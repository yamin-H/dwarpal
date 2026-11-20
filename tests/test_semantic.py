import asyncio

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient

from app.api.schemas import ChatRequest, Message
from app.cache.exact import CachedCompletion, MemoryCache
from app.cache.semantic import SemanticCache, eligible
from app.config import Settings
from app.main import create_app

URL = "/v1/chat/completions"
BN = "যাকাত কত টাকা দিতে হয়"
BANGLISH = "zakat koto taka dite hoy"
GOLD, SILVER = "zakat on gold", "zakat on silver"

VECTORS = {
    BANGLISH: [1.0, 0.0, 0.0, 0.0],
    BN: [0.98, 0.2, 0.0, 0.0],        # cosine ~0.98 with BANGLISH: a paraphrase
    GOLD: [0.0, 0.0, 1.0, 0.1],
    SILVER: [0.0, 0.0, 1.0, 0.25],    # cosine ~0.989 with GOLD: a near-miss
}
ANSWER = CachedCompletion("cached answer", 3, 2)


class FakeEmbedder:
    async def embed_one(self, text):
        return list(VECTORS[text.strip()])


class BrokenEmbedder:
    async def embed_one(self, text):
        raise RuntimeError("model unavailable")


def make_cache(threshold=0.95, ttl=3600, clock=None, embedder=None):
    extra = {"clock": clock} if clock else {}
    return SemanticCache(
        AsyncQdrantClient(location=":memory:"), embedder or FakeEmbedder(),
        threshold=threshold, ttl_seconds=ttl, **extra,
    )


def req(text, model="auto", extra=None):
    return ChatRequest(model=model, messages=(extra or []) + [Message(role="user", content=text)])


async def store_then_lookup(cache, stored_req, lookup_req, stored_tenant="tenant-a",
                            lookup_tenant="tenant-a"):
    first = await cache.lookup(stored_tenant, stored_req)
    await cache.store(stored_tenant, stored_req, first.vector, ANSWER)
    return await cache.lookup(lookup_tenant, lookup_req)


def test_paraphrase_hits_above_threshold():
    res = asyncio.run(store_then_lookup(make_cache(), req(BANGLISH), req(BN)))
    assert res.hit == ANSWER
    assert 0.97 < res.score <= 1.0


def test_near_miss_is_decided_by_the_threshold():
    loose = asyncio.run(store_then_lookup(make_cache(0.95), req(GOLD), req(SILVER)))
    strict = asyncio.run(store_then_lookup(make_cache(0.995), req(GOLD), req(SILVER)))
    assert loose.hit == ANSWER   # too loose: serves the gold answer for silver
    assert strict.hit is None    # this is why the threshold comes from data, not a guess


def test_tenants_never_share_entries():
    res = asyncio.run(store_then_lookup(
        make_cache(), req(BANGLISH), req(BN), stored_tenant="tenant-a", lookup_tenant="tenant-b"
    ))
    assert res.hit is None


def test_different_model_is_a_different_context():
    res = asyncio.run(store_then_lookup(make_cache(), req(BANGLISH), req(BN, model="mock-echo")))
    assert res.hit is None


def test_entries_expire():
    now = {"t": 1000.0}
    cache = make_cache(ttl=60, clock=lambda: now["t"])

    async def scenario():
        first = await cache.lookup("tenant-a", req(BANGLISH))
        await cache.store("tenant-a", req(BANGLISH), first.vector, ANSWER)
        now["t"] = 1030.0
        fresh = await cache.lookup("tenant-a", req(BN))
        now["t"] = 1100.0
        expired = await cache.lookup("tenant-a", req(BN))
        return fresh.hit, expired.hit

    fresh, expired = asyncio.run(scenario())
    assert fresh == ANSWER and expired is None


def test_only_single_turn_questions_are_eligible():
    assert eligible(req(BN))
    assert eligible(req(BN, extra=[Message(role="system", content="Be brief")]))
    history = [Message(role="user", content="earlier"), Message(role="assistant", content="reply")]
    assert not eligible(req(BN, extra=history))
    assert not eligible(req("x" * 1001))


def test_embedder_failure_is_a_miss_not_an_error():
    res = asyncio.run(make_cache(embedder=BrokenEmbedder()).lookup("tenant-a", req(BN)))
    assert res.hit is None and res.vector is None


@pytest.fixture
def client():
    settings = Settings(admin_key="test-admin-key", database_url="sqlite://", _env_file=None)
    return TestClient(create_app(settings, cache=MemoryCache(), semantic=make_cache()))


def chat(client, headers, text, **kw):
    body = {"model": "auto", "messages": [{"role": "user", "content": text}], **kw}
    return client.post(URL, json=body, headers=headers)


def test_paraphrase_is_served_from_the_semantic_cache(client, auth):
    first, second = chat(client, auth, BANGLISH), chat(client, auth, BN)
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT-SEMANTIC"
    assert float(second.headers["x-cache-score"]) >= 0.95
    assert second.json()["choices"][0]["message"]["content"] == "Mock reply to: " + BANGLISH


def test_semantic_hit_can_be_streamed(client, auth):
    chat(client, auth, BANGLISH)
    r = chat(client, auth, BN, stream=True)
    assert r.headers["x-cache"] == "HIT-SEMANTIC"
    assert "Mock" in r.text and r.text.strip().endswith("data: [DONE]")


def test_semantic_cache_is_tenant_isolated_through_the_api(client, make_auth):
    a, b = make_auth("tenant-a"), make_auth("tenant-b")
    chat(client, a, BANGLISH)
    assert chat(client, b, BN).headers["x-cache"] == "MISS"


def test_time_sensitive_question_never_reaches_the_embedder(client, auth):
    r = chat(client, auth, "namaz er time ajke koyta")  # not in VECTORS: would raise if embedded
    assert r.headers["x-cache"] == "SKIP"

def test_semantic_hits_are_counted_in_usage(client, auth):
    chat(client, auth, BANGLISH)   # miss, calls the provider
    chat(client, auth, BN)         # semantic hit, then backfilled into the exact cache
    chat(client, auth, BN)         # exact hit: no embedding needed
    s = client.app.state.store.usage_summary("demo-app")
    assert (s["requests"], s["cache_hits"], s["semantic_hits"]) == (3, 2, 1)


def test_embedder_outage_does_not_break_requests():
    settings = Settings(admin_key="test-admin-key", database_url="sqlite://", _env_file=None)
    c = TestClient(create_app(settings, cache=MemoryCache(),
                              semantic=make_cache(embedder=BrokenEmbedder())))
    admin = {"Authorization": "Bearer test-admin-key"}
    c.post("/admin/tenants", json={"id": "demo-app", "name": "d"}, headers=admin)
    key = c.post("/admin/tenants/demo-app/keys", headers=admin).json()["api_key"]
    r = chat(c, {"Authorization": f"Bearer {key}"}, BN)
    assert r.status_code == 200 and r.headers["x-cache"] == "MISS"