from app.api.schemas import ChatRequest, Message
from app.config import Settings
from app.core.errors import ApiError
from app.routing.providers import Completion

ADMIN = {"Authorization": "Bearer test-admin-key"}
URL = "/v1/chat/completions"


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


def app_settings(**kw) -> Settings:
    return Settings(admin_key="test-admin-key", database_url="sqlite://", _env_file=None, **kw)


def create_tenant(client, tenant_id="demo-app", **body):
    payload = {"id": tenant_id, "name": tenant_id, **body}
    r = client.post("/admin/tenants", json=payload, headers=ADMIN)
    assert r.status_code == 201, r.text
    key = client.post(f"/admin/tenants/{tenant_id}/keys", headers=ADMIN).json()["api_key"]
    return {"Authorization": f"Bearer {key}"}


def chat(client, headers, text, model="auto", **extra):
    body = {"model": model, "messages": [{"role": "user", "content": text}], **extra}
    return client.post(URL, json=body, headers=headers)


from datetime import datetime, timedelta, timezone


class Clock:
    def __init__(self, start=None):
        self.t = start or datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)

    def set(self, t):
        self.t = t


def make_store(clock=None):
    from app.core.store import Store
    from app.db.session import init_db, make_engine, make_session_factory

    engine = make_engine("sqlite://")
    init_db(engine)
    return Store(make_session_factory(engine), clock=clock)