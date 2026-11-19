import json
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest
from app.core.auth import require_tenant
from app.core.errors import ApiError
from app.core.tenants import Tenant
from app.routing.providers import Provider, get_provider

router = APIRouter(prefix="/v1", tags=["chat"])


def _chunk(cid: str, created: int, model: str, delta: dict, finish: str | None = None) -> str:
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _sse(provider: Provider, req: ChatRequest, cid: str, created: int):
    yield _chunk(cid, created, req.model, {"role": "assistant"})
    async for piece in provider.stream(req):
        yield _chunk(cid, created, req.model, {"content": piece})
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
    # ...rest of the function stays exactly the same

    completion = await provider.complete(req)
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