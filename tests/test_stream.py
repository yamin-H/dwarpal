import json

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())
URL = "/v1/chat/completions"
PAYLOAD = {"model": "auto", "stream": True,
           "messages": [{"role": "user", "content": "hello world"}]}


def parse(text: str) -> list[str]:
    return [line[6:] for line in text.splitlines() if line.startswith("data: ")]


def test_stream_format_and_content():
    r = client.post(URL, json=PAYLOAD)
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse(r.text)
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert len(chunks) > 3
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text == "Mock reply to: hello world"