import pytest
from fastapi.testclient import TestClient
from helpers import ADMIN, FakeProvider, app_settings, chat, create_tenant
from qdrant_client import AsyncQdrantClient

from app.cache.exact import MemoryCache
from app.cache.semantic import SemanticCache
from app.main import create_app
from app.routing.router import Router, RoutingConfig

GOLD, SILVER = "zakat on gold", "zakat on silver"
VECTORS = {GOLD: [0.0, 0.0, 1.0, 0.1], SILVER: [0.0, 0.0, 1.0, 0.25]}  # cosine ~0.989


class FakeEmbedder:
    async def embed_one(self, text):
        return list(VECTORS[text.strip()])


def test_tenant_defaults(client):
    r = client.post("/admin/tenants", json={"id": "demo-app", "name": "Demo"}, headers=ADMIN)
    body = r.json()
    assert (body["cache_enabled"], body["allow_fallback"], body["active"]) == (True, True, True)
    assert body["semantic_threshold"] is None and body["monthly_token_budget"] is None


def test_tenant_options_roundtrip(client):
    r = client.post("/admin/tenants", headers=ADMIN, json={
        "id": "bank-app", "name": "Bank", "cache_enabled": False, "allow_fallback": False,
        "semantic_threshold": 0.97, "monthly_token_budget": 1000, "monthly_cost_budget_usd": 2.5,
    })
    body = r.json()
    assert (body["cache_enabled"], body["allow_fallback"], body["semantic_threshold"]) == (
        False, False, 0.97)
    assert body["monthly_token_budget"] == 1000 and body["monthly_cost_budget_usd"] == 2.5
    assert client.get("/admin/tenants/bank-app", headers=ADMIN).json() == body


@pytest.mark.parametrize("bad", [
    {"semantic_threshold": 0.2}, {"semantic_threshold": 1.5},
    {"monthly_token_budget": 0}, {"monthly_cost_budget_usd": -1},
])
def test_invalid_options_are_rejected(client, bad):
    r = client.post("/admin/tenants", headers=ADMIN, json={"id": "demo-app", "name": "d", **bad})
    assert r.status_code == 422


def test_patch_changes_and_clears_limits(client):
    client.post("/admin/tenants", json={"id": "demo-app", "name": "d"}, headers=ADMIN)
    r = client.patch("/admin/tenants/demo-app", headers=ADMIN,
                     json={"monthly_token_budget": 500, "cache_enabled": False})
    assert r.json()["monthly_token_budget"] == 500 and r.json()["cache_enabled"] is False
    r = client.patch("/admin/tenants/demo-app", headers=ADMIN, json={"monthly_token_budget": None})
    assert r.json()["monthly_token_budget"] is None


def test_patch_validation_and_auth(client):
    client.post("/admin/tenants", json={"id": "demo-app", "name": "d"}, headers=ADMIN)
    assert client.patch("/admin/tenants/demo-app", headers=ADMIN, json={"name": None}).status_code == 422
    assert client.patch("/admin/tenants/demo-app", headers=ADMIN, json={}).status_code == 400
    assert client.patch("/admin/tenants/ghost-app", headers=ADMIN, json={"name": "x"}).status_code == 404
    assert client.patch("/admin/tenants/demo-app", json={"name": "x"}).status_code == 401


def test_kill_switch_blocks_and_restores_a_tenant(client):
    headers = create_tenant(client)
    assert chat(client, headers, "hi").status_code == 200
    client.patch("/admin/tenants/demo-app", headers=ADMIN, json={"active": False})
    assert chat(client, headers, "hi").status_code == 401
    client.patch("/admin/tenants/demo-app", headers=ADMIN, json={"active": True})
    assert chat(client, headers, "hi").status_code == 200


def test_cache_opt_out(client):
    c = TestClient(create_app(app_settings(), cache=MemoryCache()))
    opted_out = create_tenant(c, "private-app", cache_enabled=False)
    for _ in range(2):
        r = chat(c, opted_out, "hello world")
        assert r.headers["x-cache"] == "SKIP" and r.headers["x-cache-reason"] == "tenant-policy"
    normal = create_tenant(c, "normal-app")
    chat(c, normal, "hello world")
    assert chat(c, normal, "hello world").headers["x-cache"] == "HIT"


def test_per_tenant_semantic_threshold():
    semantic = SemanticCache(
        AsyncQdrantClient(location=":memory:"), FakeEmbedder(), threshold=0.95, ttl_seconds=3600
    )
    c = TestClient(create_app(app_settings(), semantic=semantic))
    loose = create_tenant(c, "loose-app")
    strict = create_tenant(c, "strict-app", semantic_threshold=0.995)
    chat(c, loose, GOLD)
    assert chat(c, loose, SILVER).headers["x-cache"] == "HIT-SEMANTIC"  # the risky near-miss
    chat(c, strict, GOLD)
    assert chat(c, strict, SILVER).headers["x-cache"] == "MISS"


def test_fallback_can_be_disabled_per_tenant():
    providers = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f")}
    router = Router(lambda name: providers[name], RoutingConfig(chains={"m": ["f"]}))
    c = TestClient(create_app(app_settings(), router=router))
    flexible = create_tenant(c, "flex-app", allowed_models=["m"])
    pinned = create_tenant(c, "pinned-app", allowed_models=["m"], allow_fallback=False)
    ok = chat(c, flexible, "hi", model="m")
    assert ok.status_code == 200 and ok.headers["x-provider"] == "f"
    assert chat(c, pinned, "hi", model="m").status_code == 502