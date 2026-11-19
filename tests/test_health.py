from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz():
    assert client.get("/readyz").json() == {"status": "ready"}