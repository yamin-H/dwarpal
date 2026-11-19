from app.routing import providers

URL = "/v1/chat/completions"
BODY = {"model": "auto", "messages": [{"role": "user", "content": "hello world"}]}


def summary(client, tenant_id="demo-app"):
    return client.app.state.store.usage_summary(tenant_id)


def test_successful_request_is_recorded(client, auth):
    assert client.post(URL, json=BODY, headers=auth).status_code == 200
    s = summary(client)
    assert s["requests"] == 1 and s["errors"] == 0
    assert s["total_tokens"] > 0


def test_streaming_request_is_recorded(client, auth):
    client.post(URL, json={**BODY, "stream": True}, headers=auth)
    s = summary(client)
    assert s["requests"] == 1 and s["completion_tokens"] > 0


def test_upstream_error_is_recorded_as_error(client, make_auth, monkeypatch):
    async def boom(**kw):
        raise RuntimeError("down")

    monkeypatch.setattr(providers.litellm, "acompletion", boom)
    h = make_auth(models=["gpt-4o-mini"])
    r = client.post(URL, json={**BODY, "model": "gpt-4o-mini"}, headers=h)
    assert r.status_code == 502
    s = summary(client)
    assert s["requests"] == 1 and s["errors"] == 1


def test_usage_failure_never_breaks_the_request(client, auth, monkeypatch):
    def boom(**kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(client.app.state.store, "record_usage", boom)
    assert client.post(URL, json=BODY, headers=auth).status_code == 200


def test_rejected_requests_are_not_counted(client, auth):
    client.post(URL, json=BODY)  # no key
    assert summary(client)["requests"] == 0