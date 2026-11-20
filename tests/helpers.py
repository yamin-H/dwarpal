from app.api.schemas import ChatRequest, Message
from app.core.errors import ApiError
from app.routing.providers import Completion


class FakeProvider:
    def __init__(self, name, fail=False, pieces=("a", "b"), fail_after=None, code="upstream_error"):
        self.name, self.fail, self.pieces = name, fail, pieces
        self.fail_after, self.code = fail_after, code
        self.calls = 0

    def _error(self) -> ApiError:
        return ApiError(502, "boom", self.code, "api_error")

    async def complete(self, req):
        self.calls += 1
        if self.fail:
            raise self._error()
        return Completion(f"from {self.name}", 1, 1)

    async def stream(self, req):
        self.calls += 1
        if self.fail:
            raise self._error()
        for i, piece in enumerate(self.pieces):
            if self.fail_after is not None and i == self.fail_after:
                raise self._error()
            yield piece


def make_req(model="m") -> ChatRequest:
    return ChatRequest(model=model, messages=[Message(role="user", content="hi")])