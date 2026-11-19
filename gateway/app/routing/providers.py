import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Protocol
from app.config import Settings
from app.api.schemas import ChatRequest
from app.config import get_settings
from app.core.errors import ApiError


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


def get_provider(model: str, settings: Settings) -> Provider:
    if model in ("auto", "mock-echo"):
        return MockProvider(settings.mock_delay_ms)
    raise ApiError(404, f"Model '{model}' not found", "model_not_found")