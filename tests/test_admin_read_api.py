import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from helpers import ADMIN, Clock, app_settings, chat, create_tenant, make_store
from qdrant_client import AsyncQdrantClient

from app.api.schemas import ChatRequest, Message
from app.cache.exact import CachedCompletion, MemoryCache, RedisCache
from app.cache.semantic import SemanticCache
from app.main import create_app


def test_read_endpoints_require_the_admin_key(client):
    for path in ("/admin/tenants", "/admin/overview", "/admin/requests", "/admin/system"):
        assert client.get(path).status_code == 401
    assert client.delete("/admin/tenants/demo-app/cache").status_code == 401


def test_list_tenants_has_usage_keys_and_month_progress(client):
    h = create_tenant(client, monthly_token_budget=1000)
    chat(client, h, "hello world")
    t = client.get("/admin/tenants", headers=ADMIN).json()["tenants"][0]
    assert (t["id"], t["requests"], t["active_keys"]) == ("demo-app", 1, 1)
    assert t["month_tokens"] == 7 and t["monthly_token_budget"] == 1000
    assert "api_key" not in str(t) and "key_hash" not in str(t)


def test_overview_buckets_and_totals():
    clock = Clock()                                   # 2026-11-20 12:00 UTC
    store = make_store(clock)
    store.create_tenant("demo-app", "Demo")
    base = dict(tenant_id="demo-app", model="auto", stream=False)
    store.record_usage(status="ok", provider="mock", prompt_tokens=2, completion_tokens=5,
                       latency_ms=300, cost_micros=10, **base)               # 12:00
    clock.advance(-3600)                                                     # 11:00
    store.record_usage(status="ok", provider="cache", prompt_tokens=0, completion_tokens=0,
                       latency_ms=5, cost_micros=0, **base)
    store.record_usage(status="error", provider="mock", prompt_tokens=0, completion_tokens=0,
                       latency_ms=40, cost_micros=0, **base)
    clock.set(datetime(2026, 11, 20, 12, 30, tzinfo=timezone.utc))
    o = store.overview(hours=3)
    assert [p["requests"] for p in o["series"]] == [0, 2, 1]
    assert o["series"][1]["hour"] == "2026-11-20T11:00:00Z"
    t = o["totals"]
    assert (t["requests"], t["errors"], t["cache_hits"], t["tokens"]) == (3, 1, 1, 7)
    assert t["hit_rate"] == 0.333 and t["avg_hit_ms"] == 5.0 and t["avg_miss_ms"] == 300.0
    assert {p["provider"]: p["requests"] for p in o["by_provider"]} == {"mock": 2, "cache": 1}
    assert o["top_tenants"][0]["requests"] == 3


def test_overview_ignores_rows_outside_the_window():
    clock = Clock()
    store = make_store(clock)
    store.create_tenant("demo-app", "Demo")
    clock.advance(-10 * 3600)
    store.record_usage(tenant_id="demo-app", model="auto", provider="mock", stream=False,
                       status="ok", prompt_tokens=1, completion_tokens=1, latency_ms=1)
    clock.advance(10 * 3600)
    assert store.overview(hours=6)["totals"]["requests"] == 0
    assert store.overview(hours=24)["totals"]["requests"] == 1


def test_overview_endpoint_validates_hours(client):
    assert client.get("/admin/overview?hours=0", headers=ADMIN).status_code == 422
    assert client.get("/admin/overview?hours=169", headers=ADMIN).status_code == 422
    body = client.get("/admin/overview?hours=6", headers=ADMIN).json()
    assert len(body["series"]) == 6 and body["totals"]["requests"] == 0


def test_request_log_filters_and_paginates(client):
    h = create_tenant(client)
    for i in range(5):
        chat(client, h, f"question {i}")
    first = client.get("/admin/requests?limit=2", headers=ADMIN).json()
    assert len(first["requests"]) == 2 and first["next_before_id"] == first["requests"][-1]["id"]
    rest = client.get(f"/admin/requests?limit=10&before_id={first['next_before_id']}",
                      headers=ADMIN).json()
    assert len(rest["requests"]) == 3 and rest["next_before_id"] is None
    assert not {"prompt", "content", "messages", "answer"} & set(first["requests"][0])
    assert client.get("/admin/requests?status=bogus", headers=ADMIN).status_code == 422
    assert client.get("/admin/requests?tenant_id=other-app", headers=ADMIN).json()["requests"] == []


def test_system_reports_state_without_secrets(client):
    r = client.get("/admin/system", headers=ADMIN)
    body = r.json()
    assert body["checks"]["database"] == "ok" and body["checks"]["redis"] == "disabled"
    assert body["routing"]["circuits"] == {} and "auto" in body["prices"]
    assert set(body["providers_configured"]) == {
        "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"}
    assert "test-admin-key" not in r.text and "redis://" not in r.text
    assert "postgresql" not in r.text


def test_purge_clears_only_that_tenants_cache():
    c = TestClient(create_app(app_settings(), cache=MemoryCache()))
    a, b = create_tenant(c, "tenant-a"), create_tenant(c, "tenant-b")
    chat(c, a, "hello world")
    chat(c, b, "hello world")
    assert chat(c, a, "hello world").headers["x-cache"] == "HIT"
    r = c.delete("/admin/tenants/tenant-a/cache", headers=ADMIN)
    assert r.status_code == 200 and r.json()["exact_deleted"] == 1
    assert chat(c, a, "hello world").headers["x-cache"] == "MISS"
    assert chat(c, b, "hello world").headers["x-cache"] == "HIT"


def test_purge_unknown_tenant_is_404(client):
    assert client.delete("/admin/tenants/ghost-app/cache", headers=ADMIN).status_code == 404


def test_redis_purge_and_ping():
    from fakeredis import aioredis as fake

    async def scenario():
        redis_client = fake.FakeRedis(decode_responses=True)
        cache = RedisCache(redis_client, ttl_seconds=60)
        await cache.set("cache:v1:tenant-a:1", CachedCompletion("x", 1, 1))
        await cache.set("cache:v1:tenant-a:2", CachedCompletion("x", 1, 1))
        await cache.set("cache:v1:tenant-b:1", CachedCompletion("x", 1, 1))
        return (await cache.ping(), await cache.purge_tenant("tenant-a"),
                await cache.get("cache:v1:tenant-b:1"))

    ping, deleted, other = asyncio.run(scenario())
    assert (ping, deleted) == ("ok", 2) and other is not None


def test_semantic_purge_removes_only_the_tenants_entries():
    class Embedder:
        async def embed_one(self, text):
            return [1.0, 0.0, 0.0, 0.0]

    cache = SemanticCache(AsyncQdrantClient(location=":memory:"), Embedder(),
                          threshold=0.9, ttl_seconds=3600)
    req = ChatRequest(messages=[Message(role="user", content="zakat")])

    async def scenario():
        for tenant in ("tenant-a", "tenant-b"):
            found = await cache.lookup(tenant, req)
            await cache.store(tenant, req, found.vector, CachedCompletion("answer", 1, 1))
        assert await cache.purge_tenant("tenant-a") is True
        return (await cache.lookup("tenant-a", req)).hit, (await cache.lookup("tenant-b", req)).hit

    gone, kept = asyncio.run(scenario())
    assert gone is None and kept is not None
