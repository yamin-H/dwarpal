import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import litellm

from app.api.schemas import ChatRequest
from app.config import Settings
from app.core.errors import ApiError

log = logging.getLogger("dwarpal")
MOCK_MODELS = ("auto", "mock-echo")


@dataclass
class Completion:
    content: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str = "stop"


class Provider(Protocol):
    name: str

    async def complete(self, req: ChatRequest) -> Completion: ...

    def stream(self, req: ChatRequest) -> AsyncIterator[str]: ...


def _last_user_message(req: ChatRequest) -> str:
    for m in reversed(req.messages):
        if m.role == "user":
            return m.content
    return ""


class MockProvider:
    name = "mock"

    def __init__(self, delay_ms: int = 0) -> None:
        self.delay = delay_ms / 1000

    def _reply(self, req: ChatRequest) -> str:
        return f"Mock reply to: {_last_user_message(req)}"

    async def complete(self, req: ChatRequest) -> Completion:
        if self.delay:
            await asyncio.sleep(self.delay)
        text = self._reply(req)
        prompt_tokens = sum(len(m.content.split()) for m in req.messages)
        return Completion(text, prompt_tokens, len(text.split()))

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        for i, word in enumerate(self._reply(req).split(" ")):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield word if i == 0 else " " + word


def _upstream_error(exc: Exception) -> ApiError:
    log.exception("upstream provider failure: %s", type(exc).__name__)
    return ApiError(502, "Upstream provider error.", "upstream_error", "api_error")


class LiteLLMProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        self.name = f"litellm:{model}"

    def _kwargs(self, req: ChatRequest) -> dict:
        kw = {
            "model": self.model,
            "messages": [m.model_dump() for m in req.messages],
            "timeout": 60,
        }
        if req.max_tokens:
            kw["max_tokens"] = req.max_tokens
        if req.temperature is not None:
            kw["temperature"] = req.temperature
        return kw

    async def complete(self, req: ChatRequest) -> Completion:
        try:
            resp = await litellm.acompletion(**self._kwargs(req))
        except Exception as exc:
            raise _upstream_error(exc) from exc
        choice = resp.choices[0]
        return Completion(
            choice.message.content or "",
            resp.usage.prompt_tokens,
            resp.usage.completion_tokens,
            choice.finish_reason or "stop",
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        try:
            resp = await litellm.acompletion(**self._kwargs(req), stream=True)
            async for chunk in resp:
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        except Exception as exc:
            raise _upstream_error(exc) from exc


def get_provider(model: str, settings: Settings) -> Provider:
    if model in MOCK_MODELS:
        return MockProvider(settings.mock_delay_ms)
    return LiteLLMProvider(model)