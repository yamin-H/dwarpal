URL = "/v1/chat/completions"


def body(**kw):
    return {"model": "auto", "messages": [{"role": "user", "content": "hello world"}], **kw}


def test_returns_openai_shape(client, auth):
    r = client.post(URL, json=body(), headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Mock reply to: hello world"
    u = data["usage"]
    assert u["total_tokens"] == u["prompt_tokens"] + u["completion_tokens"]



def test_empty_messages_rejected(client, auth):
    r = client.post(URL, json={"model": "auto", "messages": []}, headers=auth)
    assert r.status_code == 422