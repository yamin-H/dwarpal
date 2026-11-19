import time
import uuid

from fastapi import APIRouter

from app.api.schemas import ChatRequest
from app.routing.providers import get_provider

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat/completions")
async def chat_completions(req: ChatRequest):
    provider = get_provider(req.model)
    completion = await provider.complete(req)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
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