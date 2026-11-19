import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import ChatRequest, Message
from app.cache.exact import CachedCompletion, MemoryCache, RedisCache, make_key
from app.cache.replay import replay_pieces
from app.config import Settings
from app.main import create_app
from app.routing import providers

URL = "/v1/chat/completions"
BODY = {"model": "auto", "messages": [{"role": "user", "content": "hello world"}]}


@pytest.fixture
def client():
    settings = Settings(admin_key="test-admin-key", database_url="sqlite://", _env_file=None)
    return TestClient(create_app(settings, cache=MemoryCache()))


def x_cache(r):
    return r.headers["x-cache"]


def test_second_identical_request_is_a_hit(client, auth):
    first = client.post(URL, json=BODY, headers=auth)
    second = client.post(URL, json=BODY, headers=auth)
    assert x_cache(first) == "MISS" and x_cache(second) == "HIT"
    assert first.json()["choices"] == second.json()["choices"] or (
        first.json()["choices"][0]["message"] == second.json()["choices"][0]["message"]
    )


def test_different_prompt_is_a_miss(client, auth):
    client.post(URL, json=BODY, headers=auth)
    other = {"model": "auto", "messages": [{"role": "user", "content": "something else"}]}
    assert x_cache(client.post(URL, json=other, headers=auth)) == "MISS"


def test_cache_is_isolated_between_tenants(client, make_auth):
    a, b = make_auth("tenant-a"), make_auth("tenant-b")
    assert x_cache(client.post(URL, json=BODY, headers=a)) == "MISS"
    assert x_cache(client.post(URL, json=BODY, headers=a)) == "HIT"
    assert x_cache(client.post(URL, json=BODY, headers=b)) == "MISS"  # never A's entry


def test_bypass_header_skips_the_cache(client, auth):
    client.post(URL, json=BODY, headers=auth)
    r = client.post(URL, json=BODY, headers={**auth, "X-Dwarpal-Cache": "bypass"})
    assert x_cache(r) == "BYPASS"


def test_streamed_answer_is_cached_for_non_stream_requests(client, auth):
    streamed = client.post(URL, json={**BODY, "stream": True}, headers=auth)
    assert x_cache(streamed) == "MISS"
    plain = client.post(URL, json=BODY, headers=auth)
    assert x_cache(plain) == "HIT"
    assert plain.json()["choices"][0]["message"]["content"] == "Mock reply to: hello world"


def test_stream_hit_replays_the_same_text(client, auth):
    client.post(URL, json=BODY, headers=auth)
    r = client.post(URL, json={**BODY, "stream": True}, headers=auth)
    assert x_cache(r) == "HIT"
    events = [ln[6:] for ln in r.text.splitlines() if ln.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text == "Mock reply to: hello world"


def test_errors_are_not_cached(client, make_auth, monkeypatch):
    calls = {"n": 0}

    async def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("down")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok now"),
                                     finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
        )

    monkeypatch.setattr(providers.litellm, "acompletion", flaky)
    h = make_auth(models=["gpt-4o-mini"])
    body = {**BODY, "model": "gpt-4o-mini"}
    assert client.post(URL, json=body, headers=h).status_code == 502
    second = client.post(URL, json=body, headers=h)
    assert second.status_code == 200 and x_cache(second) == "MISS"
    assert calls["n"] == 2


def req(content="hi", model="auto", temperature=None):
    return ChatRequest(model=model, messages=[Message(role="user", content=content)],
                       temperature=temperature)


def test_cache_key_properties():
    assert make_key("t-one", req("hi")) == make_key("t-one", req("  hi  "))
    assert make_key("t-one", req("hi")) != make_key("t-two", req("hi"))
    assert make_key("t-one", req("hi")) != make_key("t-one", req("hi", model="mock-echo"))
    assert make_key("t-one", req("hi")) != make_key("t-one", req("hi", temperature=0.7))


def test_replay_pieces_rebuild_the_text():
    text = "Mock reply to: hello world"
    assert "".join(replay_pieces(text)) == text
    assert replay_pieces("") == []


def test_redis_cache_roundtrip_and_ttl():
    from fakeredis import aioredis as fake

    async def scenario():
        redis_client = fake.FakeRedis(decode_responses=True)
        cache = RedisCache(redis_client, ttl_seconds=60)
        await cache.set("k", CachedCompletion("hi", 1, 2))
        return await cache.get("k"), await redis_client.ttl("k"), await cache.get("missing")

    got, ttl, missing = asyncio.run(scenario())
    assert got == CachedCompletion("hi", 1, 2)
    assert 0 < ttl <= 60
    assert missing is None

def test_cache_hit_is_recorded_as_a_hit_with_zero_provider_tokens(client, auth):
    client.post(URL, json=BODY, headers=auth)   # miss, calls the provider
    client.post(URL, json=BODY, headers=auth)   # hit
    s = client.app.state.store.usage_summary("demo-app")
    assert s["requests"] == 2
    assert s["cache_hits"] == 1
    assert s["cache_hit_rate"] == 0.5
    first_only = s["completion_tokens"]
    client.post(URL, json=BODY, headers=auth)   # another hit adds no provider tokens
    assert client.app.state.store.usage_summary("demo-app")["completion_tokens"] == first_only

def test_redis_cache_fails_open():
    class BrokenRedis:
        async def get(self, key):
            raise ConnectionError("down")

        async def set(self, key, value, ex=None):
            raise ConnectionError("down")

    cache = RedisCache(BrokenRedis(), ttl_seconds=60)

    async def scenario():
        await cache.set("k", CachedCompletion("hi", 1, 2))
        return await cache.get("k")

    assert asyncio.run(scenario()) is None