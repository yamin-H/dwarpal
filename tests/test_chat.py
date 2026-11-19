from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())
URL = "/v1/chat/completions"


def body(**kw):
    return {"model": "auto", "messages": [{"role": "user", "content": "hello world"}], **kw}


def test_returns_openai_shape():
    r = client.post(URL, json=body())
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Mock reply to: hello world"
    u = data["usage"]
    assert u["total_tokens"] == u["prompt_tokens"] + u["completion_tokens"]


def test_unknown_model_gives_openai_style_error():
    r = client.post(URL, json=body(model="nope"))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "model_not_found"


def test_empty_messages_rejected():
    r = client.post(URL, json={"model": "auto", "messages": []})
    assert r.status_code == 422