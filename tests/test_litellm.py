from types import SimpleNamespace

from app.routing import providers

URL = "/v1/chat/completions"


def body(**kw):
    return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}], **kw}


def fake_response(text="Hello from fake"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
    )


def fake_chunks():
    async def gen():
        for piece in ["Hel", "lo"]:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))])

    return gen()


def test_litellm_completion(client, make_auth, monkeypatch):
    async def fake(**kw):
        assert kw["model"] == "gpt-4o-mini"
        return fake_response()

    monkeypatch.setattr(providers.litellm, "acompletion", fake)
    h = make_auth(models=["gpt-4o-mini"])
    r = client.post(URL, json=body(), headers=h)
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "Hello from fake"
    assert r.json()["usage"]["total_tokens"] == 7


def test_litellm_streaming(client, make_auth, monkeypatch):
    async def fake(**kw):
        assert kw["stream"] is True
        return fake_chunks()

    monkeypatch.setattr(providers.litellm, "acompletion", fake)
    h = make_auth(models=["gpt-4o-mini"])
    r = client.post(URL, json=body(stream=True), headers=h)
    assert "Hel" in r.text and "lo" in r.text
    assert r.text.strip().endswith("data: [DONE]")


def test_upstream_failure_returns_502_without_leaking_details(client, make_auth, monkeypatch):
    async def boom(**kw):
        raise RuntimeError("secret-key-sk-123 leaked in message")

    monkeypatch.setattr(providers.litellm, "acompletion", boom)
    h = make_auth(models=["gpt-4o-mini"])
    r = client.post(URL, json=body(), headers=h)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "upstream_error"
    assert "secret" not in r.text


def test_stream_failure_emits_error_event(client, make_auth, monkeypatch):
    async def boom(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(providers.litellm, "acompletion", boom)
    h = make_auth(models=["gpt-4o-mini"])
    r = client.post(URL, json=body(stream=True), headers=h)
    assert "upstream_error" in r.text
    assert r.text.strip().endswith("data: [DONE]")


def test_model_not_enabled_never_reaches_provider(client, auth, monkeypatch):
    async def must_not_run(**kw):
        raise AssertionError("provider called")

    monkeypatch.setattr(providers.litellm, "acompletion", must_not_run)
    assert client.post(URL, json=body(), headers=auth).status_code == 403