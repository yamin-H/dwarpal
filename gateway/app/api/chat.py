import json
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest
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
async def chat_completions(req: ChatRequest):
    provider = get_provider(req.model)
    cid, created = f"chatcmpl-{uuid.uuid4().hex[:24]}", int(time.time())

    if req.stream:
        return StreamingResponse(
            _sse(provider, req, cid, created),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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