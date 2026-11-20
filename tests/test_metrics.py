import asyncio

import pytest
from fastapi.testclient import TestClient
from helpers import FakeProvider, make_req

from app.cache.exact import MemoryCache
from app.config import Settings
from app.main import create_app
from app.observability.metrics import Metrics
from app.routing.router import Router, RoutingConfig

URL = "/v1/chat/completions"
BODY = {"model": "auto", "messages": [{"role": "user", "content": "hello world"}]}


@pytest.fixture
def client():
    settings = Settings(admin_key="test-admin-key", database_url="sqlite://", _env_file=None)
    return TestClient(create_app(settings, cache=MemoryCache()))


def sample(client, name, **labels):
    return client.app.state.metrics.registry.get_sample_value(name, labels)


def test_metrics_endpoint_exposes_prometheus_text(client, auth):
    client.post(URL, json=BODY, headers=auth)
    r = client.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "dwarpal_requests_total" in r.text


def test_request_counters_and_histograms(client, auth):
    client.post(URL, json=BODY, headers=auth)  # miss
    client.post(URL, json=BODY, headers=auth)  # exact hit
    base = dict(tenant="demo-app", model="auto", status="ok")
    assert sample(client, "dwarpal_requests_total", cache="MISS", **base) == 1
    assert sample(client, "dwarpal_requests_total", cache="HIT", **base) == 1
    assert sample(client, "dwarpal_request_duration_seconds_count", cache="MISS") == 1
    assert sample(client, "dwarpal_tokens_total", tenant="demo-app", type="completion") > 0


def test_streaming_records_time_to_first_token(client, auth):
    client.post(URL, json={**BODY, "stream": True}, headers=auth)
    assert sample(client, "dwarpal_ttft_seconds_count", source="mock") == 1
    client.post(URL, json={**BODY, "stream": True}, headers=auth)  # now a replayed hit
    assert sample(client, "dwarpal_ttft_seconds_count", source="cache") == 1


def test_http_status_classes_are_counted(client, auth):
    client.post(URL, json=BODY)  # no key: 401
    assert sample(client, "dwarpal_http_responses_total", status_class="4xx") == 1


def test_model_labels_are_bounded():
    m = Metrics(max_labels=2)
    for model in ["a", "b", "c", "d"]:
        m.observe_request(tenant="t", model=model, status="ok", cache="MISS",
                          duration_s=0.1, prompt_tokens=1, completion_tokens=1)
    base = dict(tenant="t", status="ok", cache="MISS")
    get = m.registry.get_sample_value
    assert get("dwarpal_requests_total", {**base, "model": "other"}) == 2
    assert get("dwarpal_requests_total", {**base, "model": "a"}) == 1


def test_provider_and_circuit_metrics():
    m, now = Metrics(), {"t": 0.0}
    providers = {"m": FakeProvider("p-m", fail=True), "f": FakeProvider("p-f")}
    cfg = RoutingConfig(chains={"m": ["f"]}, cooldown_seconds=30, failure_threshold=2)
    router = Router(lambda n: providers[n], cfg, metrics=m, clock=lambda: now["t"])
    m.bind_router(router)
    for _ in range(2):
        asyncio.run(router.provider_for("m").complete(make_req()))
    get = m.registry.get_sample_value
    assert get("dwarpal_provider_calls_total", {"provider": "p-m", "outcome": "failure"}) == 2
    assert get("dwarpal_provider_calls_total", {"provider": "p-f", "outcome": "success"}) == 2
    assert get("dwarpal_circuit_opened_total", {"model": "m"}) == 1
    assert get("dwarpal_provider_circuit_open", {"model": "m"}) == 1.0
    now["t"] = 31.0  # the gauge recovers by itself when the cooldown ends
    assert get("dwarpal_provider_circuit_open", {"model": "m"}) == 0.0


def test_metrics_failure_never_breaks_requests(client, auth, monkeypatch):
    def boom(**kw):
        raise RuntimeError("metrics down")

    monkeypatch.setattr(client.app.state.metrics, "observe_request", boom)
    assert client.post(URL, json=BODY, headers=auth).status_code == 200


def test_metrics_never_contain_prompts_or_keys(client, auth):
    client.post(URL, json=BODY, headers=auth)
    text = client.get("/metrics").text
    assert "hello world" not in text and auth["Authorization"].split()[1] not in text