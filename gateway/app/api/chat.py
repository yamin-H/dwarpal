import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.schemas import ChatRequest
from app.cache.exact import CachedCompletion, make_key
from app.cache.policy import cache_decision
from app.cache.replay import replay_pieces
from app.core.auth import require_tenant
from app.core.errors import ApiError
from app.core.tenants import Tenant
from app.routing.providers import Provider, get_provider

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


def _usage_recorder(request: Request, tenant: Tenant, req: ChatRequest, provider_name: str):
    store = request.app.state.store
    start = time.perf_counter()
    prompt_estimate = sum(_tokens(m.content) for m in req.messages)

    async def record(status: str, prompt_tokens: int | None = None, completion_tokens: int = 0):
        try:  # usage logging must never break a request
            await run_in_threadpool(
                store.record_usage,
                tenant_id=tenant.id,
                model=req.model,
                provider=provider_name,
                stream=req.stream,
                status=status,
                prompt_tokens=prompt_estimate if prompt_tokens is None else prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception:
            log.exception("usage logging failed")

    return record


async def _sse(provider: Provider, req: ChatRequest, cid: str, created: int, record, store):
    yield _chunk(cid, created, req.model, {"role": "assistant"})
    parts: list[str] = []
    try:
        async for piece in provider.stream(req):
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
    for piece in replay_pieces(hit.content):
        yield _chunk(cid, created, req.model, {"content": piece})
    await record("ok", 0, 0)
    yield _chunk(cid, created, req.model, {}, finish=hit.finish_reason)
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(
    req: ChatRequest, request: Request, tenant: Tenant = Depends(require_tenant)  # noqa: B008
):
    if not tenant.allows(req.model):
        raise ApiError(
            403, f"Model '{req.model}' is not enabled for this tenant.",
            "model_not_allowed", "permission_error",
        )
    provider = get_provider(req.model, request.app.state.settings)
    exact = request.app.state.cache
    semantic = request.app.state.semantic
    bypass = request.headers.get("x-dwarpal-cache", "").lower() == "bypass"
    decision = cache_decision(req)

    if not (exact.enabled or semantic.enabled):
        cache_status = "DISABLED"
    elif bypass:
        cache_status = "BYPASS"
    elif not decision.cacheable:
        cache_status = "SKIP"
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
        found = await semantic.lookup(tenant.id, req)
        vector = found.vector
        if found.hit:
            hit, hit_status, hit_score = found.hit, "HIT-SEMANTIC", found.score
            if exact_active:
                await exact.set(cache_key, hit)  # same phrasing next time skips the embedding

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
        record = _usage_recorder(
            request, tenant, req, "cache:semantic" if hit_score is not None else "cache"
        )
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

    record = _usage_recorder(request, tenant, req, provider.name)
    headers = {"X-Cache": cache_status}
    if cache_status == "SKIP":
        headers["X-Cache-Reason"] = decision.reason
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
    await store(
        completion.content, completion.completion_tokens,
        completion.prompt_tokens, completion.finish_reason,
    )
    return JSONResponse(_completion_body(cid, created, req.model, completion), headers=headers)