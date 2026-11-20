import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from helpers import (ADMIN, Clock, FakeProvider, app_settings, chat, create_tenant, make_req,
                     make_store)

from app.cache.exact import MemoryCache
from app.core.pricing import Price, PriceTable
from app.main import create_app
from app.routing import providers
from app.routing.router import Router, RoutingConfig

# "hello world" through the mock provider is 2 prompt + 5 completion = 7 tokens.


def sample(client, name, **labels):
    return client.app.state.metrics.registry.get_sample_value(name, labels)


def test_token_budget_is_a_soft_cap(client):
    h = create_tenant(client, monthly_token_budget=10)
    statuses = [chat(client, h, "hello world").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]  # 7, then 14 (overshoot), then blocked
    body = chat(client, h, "hello world").json()["error"]
    assert (body["code"], body["type"]) == ("budget_exceeded", "rate_limit_error")
    assert sample(client, "dwarpal_budget_rejections_total", tenant="demo-app", kind="tokens") == 2


def test_cost_budget_and_usage_report():
    prices = PriceTable({"mock-echo": Price(1_000_000.0, 1_000_000.0)})  # $1 per token
    c = TestClient(create_app(app_settings(), prices=prices))
    h = create_tenant(c, monthly_cost_budget_usd=5)
    assert chat(c, h, "hello world", model="mock-echo").status_code == 200  # costs $7
    blocked = chat(c, h, "hello world", model="mock-echo")
    assert blocked.status_code == 429 and "cost" in blocked.json()["error"]["message"]
    usage = c.get("/admin/tenants/demo-app/usage", headers=ADMIN).json()
    assert usage["cost_usd"] == 7.0
    assert usage["month_to_date"]["cost_budget_usd"] == 5.0
    assert usage["month_to_date"]["cost_usd"] == 7.0


def test_cost_budget_blocks_unpriced_models_before_any_provider_call(client, monkeypatch):
    async def must_not_run(**kw):
        raise AssertionError("provider called")

    monkeypatch.setattr(providers.litellm, "acompletion", must_not_run)
    h = create_tenant(client, allowed_models=["gpt-x"], monthly_cost_budget_usd=5)
    r = chat(client, h, "hi", model="gpt-x")
    assert r.status_code == 403 and r.json()["error"]["code"] == "model_not_priced"


def test_cache_hits_are_served_even_when_over_budget():
    c = TestClient(create_app(app_settings(), cache=MemoryCache()))
    h = create_tenant(c, monthly_token_budget=5)
    assert chat(c, h, "hello world").status_code == 200  # 7 tokens: now over budget
    hit = chat(c, h, "hello world")
    assert hit.status_code == 200 and hit.headers["x-cache"] == "HIT"
    assert chat(c, h, "something else").status_code == 429


def test_budgets_are_per_tenant(client):
    over = create_tenant(client, "tenant-a", monthly_token_budget=5)
    fine = create_tenant(client, "tenant-b", monthly_token_budget=5000)
    chat(client, over, "hello world")
    assert chat(client, over, "hello world").status_code == 429
    assert chat(client, fine, "hello world").status_code == 200


def test_raising_a_budget_takes_effect_immediately(client):
    h = create_tenant(client, monthly_token_budget=5)
    chat(client, h, "hello world")
    assert chat(client, h, "hello world").status_code == 429
    client.patch("/admin/tenants/demo-app", headers=ADMIN, json={"monthly_token_budget": 5000})
    assert chat(client, h, "hello world").status_code == 200


def test_month_usage_ignores_errors_and_other_months():
    clock = Clock()
    store = make_store(clock)
    store.create_tenant("demo-app", "Demo")
    common = dict(tenant_id="demo-app", model="auto", provider="mock", stream=False,
                  prompt_tokens=10, completion_tokens=5, latency_ms=1)
    store.record_usage(status="ok", cost_micros=100, **common)
    store.record_usage(status="error", cost_micros=0, **common)
    assert store.month_usage("demo-app") == (15, 100)
    clock.set(datetime(2026, 12, 1, 0, 0, 1, tzinfo=timezone.utc))  # next month
    assert store.month_usage("demo-app") == (0, 0)


def test_routed_provider_exposes_the_model_that_served():
    providers_map = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f")}
    router = Router(lambda n: providers_map[n], RoutingConfig(chains={"m": ["f"]}))
    routed = router.provider_for("m")
    asyncio.run(routed.complete(make_req()))
    assert routed.served_model == "f" and routed.name == "f"