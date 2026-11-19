import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest
from app.core.auth import require_tenant
from app.core.errors import ApiError
from app.core.tenants import Tenant
from app.routing.providers import Provider, get_provider

log = logging.getLogger("dwarpal")
router = APIRouter(prefix="/v1", tags=["chat"])


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


def _usage_recorder(request: Request, tenant: Tenant, req: ChatRequest, provider: Provider):
    store = request.app.state.store
    start = time.perf_counter()
    prompt_estimate = sum(_tokens(m.content) for m in req.messages)

    async def record(status: str, prompt_tokens: int | None = None, completion_tokens: int = 0):
        try:  # usage logging must never break a request
            await run_in_threadpool(
                store.record_usage,
                tenant_id=tenant.id,
                model=req.model,
                provider=provider.name,
                stream=req.stream,
                status=status,
                prompt_tokens=prompt_estimate if prompt_tokens is None else prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception:
            log.exception("usage logging failed")

    return record


async def _sse(provider: Provider, req: ChatRequest, cid: str, created: int, record):
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
    await record("ok", completion_tokens=_tokens("".join(parts)))
    yield _chunk(cid, created, req.model, {}, finish="stop")
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
    provider = get_provider(req.model, request.app.state.settings)
    cid, created = f"chatcmpl-{uuid.uuid4().hex[:24]}", int(time.time())
    record = _usage_recorder(request, tenant, req, provider)

    if req.stream:
        return StreamingResponse(
            _sse(provider, req, cid, created, record),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        completion = await provider.complete(req)
    except ApiError:
        await record("error")
        raise
    await record("ok", completion.prompt_tokens, completion.completion_tokens)
    return {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": completion.content},
                "finish_reason": completion.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
            "total_tokens": completion.prompt_tokens + completion.completion_tokens,
        },
    }