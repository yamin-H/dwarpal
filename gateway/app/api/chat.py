import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.budget import BudgetError, enforce_budget
from app.api.schemas import ChatRequest
from app.cache.exact import CachedCompletion, make_key
from app.cache.policy import cache_decision
from app.cache.replay import replay_pieces
from app.core.auth import require_tenant
from app.core.errors import ApiError
from app.core.tenants import Tenant
from app.routing.providers import Provider

log = logging.getLogger("dwarpal")
router = APIRouter(prefix="/v1", tags=["chat"])
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _tokens(text: str) -> int:
    return len(text.split())  # rough estimate until providers report exact usage


def _chunk(cid: str, created: int, model: str, delta: dict, finish: str | None = None) -> str:
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _completion_body(cid: str, created: int, model: str, c) -> dict:
    return {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": c.content},
                "finish_reason": c.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": c.prompt_tokens,
            "completion_tokens": c.completion_tokens,
            "total_tokens": c.prompt_tokens + c.completion_tokens,
        },
    }


class UsageRecorder:
    """Records one usage row and the matching metrics when a chat request finishes."""

    def __init__(self, request: Request, tenant: Tenant, req: ChatRequest, source, cache: str):
        self.store = request.app.state.store
        self.metrics = request.app.state.metrics
        self.prices = request.app.state.prices
        self.tenant, self.req, self.source, self.cache = tenant, req, source, cache
        self.start = time.perf_counter()
        self.prompt_estimate = sum(_tokens(m.content) for m in req.messages)
        self._first_token_seen = False

    @property
    def provider_name(self) -> str:
        return self.source if isinstance(self.source, str) else self.source.name

    @property
    def served_model(self) -> str | None:
        return None if isinstance(self.source, str) else getattr(self.source, "served_model", None)

    def first_token(self) -> None:
        if self._first_token_seen:
            return
        self._first_token_seen = True
        try:
            self.metrics.observe_ttft(self.provider_name, time.perf_counter() - self.start)
        except Exception:
            log.exception("metrics failed")

    def _cost_micros(self, status: str, prompt: int, completion: int) -> int:
        model = self.served_model
        if status != "ok" or model is None:  # errors are not billed; cache hits are free
            return 0
        cost = self.prices.cost_micros(model, prompt, completion)
        if cost is None:
            log.warning("unpriced model served", extra={"model": model})
            try:
                self.metrics.unpriced(model)
            except Exception:
                log.exception("metrics failed")
            return 0
        return cost

    async def __call__(
        self, status: str, prompt_tokens: int | None = None, completion_tokens: int = 0
    ) -> None:
        elapsed = time.perf_counter() - self.start
        prompt = self.prompt_estimate if prompt_tokens is None else prompt_tokens
        cost = self._cost_micros(status, prompt, completion_tokens)
        try:  # metrics and usage logging must never break a request
            self.metrics.observe_request(
                tenant=self.tenant.id, model=self.req.model, status=status, cache=self.cache,
                duration_s=elapsed, prompt_tokens=prompt, completion_tokens=completion_tokens,
                cost_usd=cost / 1_000_000,
            )
        except Exception:
            log.exception("metrics failed")
        try:
            await run_in_threadpool(
                self.store.record_usage,
                tenant_id=self.tenant.id,
                model=self.req.model,
                provider=self.provider_name,
                stream=self.req.stream,
                status=status,
                prompt_tokens=prompt,
                completion_tokens=completion_tokens,
                latency_ms=int(elapsed * 1000),
                cost_micros=cost,
                served_model=self.served_model,
            )
        except Exception:
            log.exception("usage logging failed")


async def _sse(provider: Provider, req: ChatRequest, cid: str, created: int, record, store):
    yield _chunk(cid, created, req.model, {"role": "assistant"})
    parts: list[str] = []
    try:
        async for piece in provider.stream(req):
            if not parts:
                record.first_token()
            parts.append(piece)
            yield _chunk(cid, created, req.model, {"content": piece})
    except ApiError as exc:
        await record("error", completion_tokens=_tokens("".join(parts)))
        err = {"error": {"message": exc.message, "type": exc.type_, "code": exc.code}}
        yield f"data: {json.dumps(err)}\n\n"
        yield "data: [DONE]\n\n"
        return
    text = "".join(parts)
    completion_tokens = _tokens(text)
    await record("ok", completion_tokens=completion_tokens)
    await store(text, completion_tokens)  # only complete answers are cached
    yield _chunk(cid, created, req.model, {}, finish="stop")
    yield "data: [DONE]\n\n"


async def _sse_replay(req: ChatRequest, cid: str, created: int, hit: CachedCompletion, record):
    yield _chunk(cid, created, req.model, {"role": "assistant"})
    for i, piece in enumerate(replay_pieces(hit.content)):
        if i == 0:
            record.first_token()
        yield _chunk(cid, created, req.model, {"content": piece})
    await record("ok", 0, 0)
    yield _chunk(cid, created, req.model, {}, finish=hit.finish_reason)
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(
    req: ChatRequest, request: Request, tenant: Tenant = Depends(require_tenant)
):
    if not tenant.allows(req.model):
        raise ApiError(
            403, f"Model '{req.model}' is not enabled for this tenant.",
            "model_not_allowed", "permission_error",
        )
    provider = request.app.state.router.provider_for(
        req.model, allow_fallback=tenant.allow_fallback
    )
    exact = request.app.state.cache
    semantic = request.app.state.semantic
    bypass = request.headers.get("x-dwarpal-cache", "").lower() == "bypass"
    decision = cache_decision(req)

    skip_reason = None
    if not (exact.enabled or semantic.enabled):
        cache_status = "DISABLED"
    elif bypass:
        cache_status = "BYPASS"
    elif not tenant.cache_enabled:
        cache_status, skip_reason = "SKIP", "tenant-policy"
    elif not decision.cacheable:
        cache_status, skip_reason = "SKIP", decision.reason
    else:
        cache_status = "MISS"
    use_cache = cache_status == "MISS"
    exact_active = use_cache and exact.enabled
    semantic_active = use_cache and semantic.enabled
    cache_key = make_key(tenant.id, req) if exact_active else None
    cid, created = f"chatcmpl-{uuid.uuid4().hex[:24]}", int(time.time())
    prompt_estimate = sum(_tokens(m.content) for m in req.messages)

    hit, hit_status, hit_score, vector = None, "", None, None
    if exact_active:
        hit = await exact.get(cache_key)
        hit_status = "HIT" if hit else ""
    if hit is None and semantic_active:
        found = await semantic.lookup(tenant.id, req, threshold=tenant.semantic_threshold)
        vector = found.vector
        if found.hit:
            hit, hit_status, hit_score = found.hit, "HIT-SEMANTIC", found.score
            if exact_active:
                await exact.set(cache_key, hit)  # same phrasing next time skips the embedding
    served_cache = hit_status if hit else cache_status
    request.state.cache = served_cache  # shows up in the request log line

    async def store(content, completion_tokens, prompt_tokens=None, finish="stop"):
        if not content:
            return
        entry = CachedCompletion(
            content, prompt_estimate if prompt_tokens is None else prompt_tokens,
            completion_tokens, finish,
        )
        if exact_active:
            await exact.set(cache_key, entry)
        if semantic_active and vector is not None:
            await semantic.store(tenant.id, req, vector, entry)

    if hit:
        try:
            await enforce_budget(request.app.state.store, request.app.state.prices, tenant, req.model)
        except BudgetError as exc:
            request.app.state.metrics.budget_rejected(tenant.id, exc.kind)
            log.warning("budget rejection", extra={"tenant": tenant.id, "kind": exc.kind})
            raise
        source = "cache:semantic" if hit_score is not None else "cache"
        record = UsageRecorder(request, tenant, req, source, served_cache)
        headers = {"X-Cache": hit_status}
        if hit_score is not None:
            headers["X-Cache-Score"] = f"{hit_score:.4f}"
        if req.stream:
            return StreamingResponse(
                _sse_replay(req, cid, created, hit, record),
                media_type="text/event-stream",
                headers={**SSE_HEADERS, **headers},
            )
        await record("ok", 0, 0)
        return JSONResponse(_completion_body(cid, created, req.model, hit), headers=headers)

    record = UsageRecorder(request, tenant, req, provider, served_cache)
    headers = {"X-Cache": cache_status}
    if skip_reason:
        headers["X-Cache-Reason"] = skip_reason
    if req.stream:
        return StreamingResponse(
            _sse(provider, req, cid, created, record, store),
            media_type="text/event-stream",
            headers={**SSE_HEADERS, **headers},
        )

    try:
        completion = await provider.complete(req)
    except ApiError:
        await record("error")
        raise
    await record("ok", completion.prompt_tokens, completion.completion_tokens)
    headers["X-Provider"] = provider.name
    await store(
        completion.content, completion.completion_tokens,
        completion.prompt_tokens, completion.finish_reason,
    )
    return JSONResponse(_completion_body(cid, created, req.model, completion), headers=headers)