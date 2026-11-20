import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from helpers import FakeProvider, make_req

from app.config import Settings
from app.core.errors import ApiError
from app.db.models import UsageRow
from app.main import create_app
from app.routing.providers import LiteLLMProvider, get_provider
from app.routing.router import Router, RoutingConfig, load_routing_config

ADMIN = {"Authorization": "Bearer test-admin-key"}


def make_router(providers, chains=None, threshold=3, cooldown=30.0, clock=None):
    cfg = RoutingConfig(chains=chains or {}, cooldown_seconds=cooldown, failure_threshold=threshold)
    kwargs = {"clock": clock} if clock else {}
    return Router(lambda name: providers[name], cfg, **kwargs)


def complete(router, model="m"):
    routed = router.provider_for(model)
    return routed, asyncio.run(routed.complete(make_req(model)))


async def collect(routed, req):
    pieces, error = [], None
    try:
        async for piece in routed.stream(req):
            pieces.append(piece)
    except ApiError as exc:
        error = exc
    return pieces, error


def test_primary_success_does_not_touch_the_fallback():
    p = {"m": FakeProvider("p"), "f": FakeProvider("f")}
    routed, result = complete(make_router(p, {"m": ["f"]}))
    assert result.content == "from p" and routed.name == "p" and p["f"].calls == 0


def test_failure_falls_back_to_the_next_provider():
    p = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f")}
    routed, result = complete(make_router(p, {"m": ["f"]}))
    assert result.content == "from f" and routed.name == "f"


def test_fallback_order_is_respected():
    p = {"m": FakeProvider("p", fail=True), "f1": FakeProvider("f1", fail=True),
         "f2": FakeProvider("f2")}
    _, result = complete(make_router(p, {"m": ["f1", "f2"]}))
    assert result.content == "from f2"


def test_all_failing_raises_one_clean_error():
    p = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f", fail=True)}
    with pytest.raises(ApiError) as e:
        complete(make_router(p, {"m": ["f"]}))
    assert (e.value.status, e.value.code) == (502, "upstream_error")
    assert "All configured providers failed" in e.value.message


def test_single_provider_failure_keeps_the_simple_message():
    with pytest.raises(ApiError) as e:
        complete(make_router({"m": FakeProvider("p", fail=True)}))
    assert e.value.message == "Upstream provider error."


def test_non_retryable_errors_are_not_masked_by_fallbacks():
    p = {"m": FakeProvider("p", fail=True, code="bad_request"), "f": FakeProvider("f")}
    with pytest.raises(ApiError) as e:
        complete(make_router(p, {"m": ["f"]}))
    assert e.value.code == "bad_request" and p["f"].calls == 0


def test_duplicate_models_in_a_chain_are_tried_once():
    r = make_router({"m": FakeProvider("p")}, {"m": ["m"]})
    assert r.candidates("m") == ["m"]


def test_circuit_opens_after_threshold_and_recovers():
    now = {"t": 0.0}
    p = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f")}
    r = make_router(p, {"m": ["f"]}, threshold=2, cooldown=30, clock=lambda: now["t"])
    complete(r)
    complete(r)
    assert p["m"].calls == 2
    complete(r)  # circuit open: primary skipped
    assert p["m"].calls == 2 and p["f"].calls == 3
    now["t"] = 31.0  # cooldown over: one probe
    p["m"].fail = False
    _, result = complete(r)
    assert p["m"].calls == 3 and result.content == "from p"
    complete(r)
    assert p["m"].calls == 4


def test_failed_probe_reopens_the_circuit_immediately():
    now = {"t": 0.0}
    p = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f")}
    r = make_router(p, {"m": ["f"]}, threshold=2, cooldown=30, clock=lambda: now["t"])
    complete(r)
    complete(r)
    now["t"] = 31.0
    complete(r)  # probe fails
    assert p["m"].calls == 3
    complete(r)  # reopened at once: skipped
    assert p["m"].calls == 3


def test_all_circuits_open_fails_open():
    p = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f", fail=True)}
    r = make_router(p, {"m": ["f"]}, threshold=1)
    with pytest.raises(ApiError):
        complete(r)
    p["m"].fail = False
    _, result = complete(r)  # both are cooling down, still tried
    assert result.content == "from p"


def test_unconfigured_models_are_never_tracked():
    p = {"x": FakeProvider("p", fail=True)}
    r = make_router(p, threshold=1)
    for _ in range(5):
        with pytest.raises(ApiError):
            complete(r, "x")
    assert r.health.snapshot() == {} and p["x"].calls == 5


def test_stream_falls_back_before_the_first_token():
    p = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f", pieces=("x", "y"))}
    routed = make_router(p, {"m": ["f"]}).provider_for("m")
    pieces, error = asyncio.run(collect(routed, make_req()))
    assert pieces == ["x", "y"] and error is None and routed.name == "f"


def test_stream_never_switches_after_the_first_token():
    p = {"m": FakeProvider("p", pieces=("a", "b", "c"), fail_after=1), "f": FakeProvider("f")}
    routed = make_router(p, {"m": ["f"]}).provider_for("m")
    pieces, error = asyncio.run(collect(routed, make_req()))
    assert pieces == ["a"] and error.code == "upstream_error" and p["f"].calls == 0


def test_stream_all_failing():
    p = {"m": FakeProvider("p", fail=True), "f": FakeProvider("f", fail=True)}
    routed = make_router(p, {"m": ["f"]}).provider_for("m")
    pieces, error = asyncio.run(collect(routed, make_req()))
    assert pieces == [] and error.code == "upstream_error"


def test_mid_stream_failure_counts_toward_the_circuit():
    p = {"m": FakeProvider("p", pieces=("a", "b"), fail_after=1), "f": FakeProvider("f")}
    r = make_router(p, {"m": ["f"]}, threshold=1)
    asyncio.run(collect(r.provider_for("m"), make_req()))
    _, result = complete(r)
    assert result.content == "from f" and p["m"].calls == 1


def test_load_routing_config(tmp_path):
    f = tmp_path / "routing.json"
    f.write_text(json.dumps({"chains": {"a": ["b"]}, "cooldown_seconds": 10, "failure_threshold": 2}))
    cfg = load_routing_config(str(f))
    assert cfg.chains == {"a": ["b"]} and cfg.cooldown_seconds == 10 and cfg.failure_threshold == 2
    assert load_routing_config("") == RoutingConfig()


@pytest.mark.parametrize("payload", [
    {"chains": []}, {"chains": {"a": "b"}}, {"chains": {"a": [1]}},
    {"failure_threshold": 0}, {"cooldown_seconds": -1},
])
def test_invalid_routing_config_is_rejected(tmp_path, payload):
    f = tmp_path / "routing.json"
    f.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_routing_config(str(f))


# --- through the HTTP API ---

def make_client(providers, chains):
    settings = Settings(admin_key="test-admin-key", database_url="sqlite://", _env_file=None)
    router = Router(lambda name: providers[name], RoutingConfig(chains=chains))
    return TestClient(create_app(settings, router=router))


def tenant_headers(client, models):
    client.post("/admin/tenants", headers=ADMIN,
                json={"id": "demo-app", "name": "d", "allowed_models": models})
    key = client.post("/admin/tenants/demo-app/keys", headers=ADMIN).json()["api_key"]
    return {"Authorization": f"Bearer {key}"}


def post(client, headers, model="m", **kw):
    body = {"model": model, "messages": [{"role": "user", "content": "hi"}], **kw}
    return client.post("/v1/chat/completions", json=body, headers=headers)


def usage_rows(client):
    with client.app.state.store._sf() as s:
        return s.query(UsageRow).all()


def test_api_serves_from_the_fallback_and_says_so():
    c = make_client({"m": FakeProvider("p", fail=True), "f": FakeProvider("f")}, {"m": ["f"]})
    r = post(c, tenant_headers(c, ["m"]))
    assert r.status_code == 200 and r.headers["x-provider"] == "f"
    assert r.json()["choices"][0]["message"]["content"] == "from f"
    assert [(x.provider, x.status) for x in usage_rows(c)] == [("f", "ok")]


def test_api_stream_uses_the_fallback():
    c = make_client({"m": FakeProvider("p", fail=True), "f": FakeProvider("f")}, {"m": ["f"]})
    r = post(c, tenant_headers(c, ["m"]), stream=True)
    assert '"content": "a"' in r.text and r.text.strip().endswith("data: [DONE]")
    assert usage_rows(c)[0].provider == "f"


def test_api_all_providers_down_returns_a_clean_502():
    c = make_client({"m": FakeProvider("p", fail=True), "f": FakeProvider("f", fail=True)},
                    {"m": ["f"]})
    r = post(c, tenant_headers(c, ["m"]))
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_error"
    rows = usage_rows(c)
    assert [x.status for x in rows] == ["error"] and rows[0].provider == "f"


def test_mock_fail_demo_chain_from_a_config_file(tmp_path):
    f = tmp_path / "routing.json"
    f.write_text(json.dumps({"chains": {"mock-fail": ["mock-echo"]}}))
    settings = Settings(admin_key="test-admin-key", database_url="sqlite://",
                        routing_config=str(f), _env_file=None)
    c = TestClient(create_app(settings))
    r = post(c, tenant_headers(c, ["mock-fail", "mock-echo"]), model="mock-fail")
    assert r.status_code == 200 and r.headers["x-provider"] == "mock"


def test_mock_fail_is_not_available_in_prod():
    settings = Settings(app_env="prod", database_url="sqlite://", _env_file=None)
    assert isinstance(get_provider("mock-fail", settings), LiteLLMProvider)