import asyncio

import httpx
from fastapi.testclient import TestClient
from helpers import app_settings, create_tenant
from outage_drill import bucket_timeline, metric_value, parse_metrics, run_drill, summarize_drill

from app.main import create_app
from app.observability.metrics import Metrics
from app.routing.providers import get_provider
from app.routing.router import Router, RoutingConfig


def test_parse_metrics_and_lookup():
    m = Metrics()
    m.provider_call("mock-fail", False)
    m.provider_call("mock-fail", False)
    m.provider_call("mock", True)
    samples = parse_metrics(m.render().decode())
    name = "dwarpal_provider_calls_total"
    assert metric_value(samples, name, provider="mock-fail", outcome="failure") == 2
    assert metric_value(samples, name, provider="mock") == 1
    assert metric_value(samples, name, provider="nobody") == 0


def test_bucket_timeline():
    records = [
        {"t": 0.5, "status": 200, "provider": "mock", "latency": 0.01},
        {"t": 4.9, "status": 502, "provider": None, "latency": 0.02},
        {"t": 5.1, "status": 200, "provider": "mock", "latency": 0.01},
    ]
    assert bucket_timeline(records) == [
        {"t": 0, "requests": 2, "ok": 1, "errors": 1, "served_by": {"mock": 1}},
        {"t": 5, "requests": 1, "ok": 1, "errors": 0, "served_by": {"mock": 1}},
    ]


def test_summarize_drill_math():
    records = [{"t": float(i), "status": 200, "provider": "mock", "latency": 0.01}
               for i in range(10)]
    calls = "dwarpal_provider_calls_total"
    before = [(calls, {"provider": "mock-fail", "outcome": "failure"}, 5.0),
              ("dwarpal_circuit_opened_total", {"model": "mock-fail"}, 1.0)]
    after = [(calls, {"provider": "mock-fail", "outcome": "failure"}, 9.0),
             ("dwarpal_circuit_opened_total", {"model": "mock-fail"}, 2.0)]
    s = summarize_drill(records, before, after, "mock-fail", "mock-fail")
    assert s["failing_calls"] == 4 and s["circuit_opened"] == 1
    assert s["calls_avoided"] == 6 and s["success_rate"] == 1.0
    assert s["served_by"] == {"mock": 10}


def test_drill_against_an_in_process_gateway():
    metrics, settings = Metrics(), app_settings()
    router = Router(lambda m: get_provider(m, settings),
                    RoutingConfig(chains={"mock-fail": ["mock-echo"]}), metrics=metrics)
    app = create_app(settings, router=router, metrics=metrics)
    headers = create_tenant(TestClient(app), allowed_models=["mock-fail"])

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async def scrape():
                return metrics.render().decode()

            return await run_drill(client, "http://test", headers, scrape, "mock-fail",
                                   "mock-fail", duration=1, rate=20)

    s = asyncio.run(scenario())
    assert s["requests"] == 20 and s["ok"] == 20 and s["success_rate"] == 1.0
    assert s["served_by"] == {"mock": 20}
    assert 3 <= s["failing_calls"] <= 5        # failure_threshold (3), then the breaker opens
    assert s["circuit_opened"] == 1
