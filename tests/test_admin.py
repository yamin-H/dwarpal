from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADMIN = {"Authorization": "Bearer test-admin-key"}


def test_admin_requires_key(client):
    assert client.post("/admin/tenants", json={"id": "abc", "name": "x"}).status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert client.post("/admin/tenants", json={"id": "abc", "name": "x"}, headers=bad).status_code == 401


def test_admin_disabled_when_no_key_configured():
    c = TestClient(create_app(Settings(admin_key="", database_url="sqlite://", _env_file=None)))
    assert c.post("/admin/tenants", json={"id": "abc", "name": "x"}).status_code == 403


def test_create_tenant_and_duplicate(client):
    body = {"id": "demo-app", "name": "Demo"}
    r = client.post("/admin/tenants", json=body, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["allowed_models"] == ["auto", "mock-echo"]
    assert client.post("/admin/tenants", json=body, headers=ADMIN).status_code == 409


def test_invalid_tenant_id_rejected(client):
    r = client.post("/admin/tenants", json={"id": "A B", "name": "x"}, headers=ADMIN)
    assert r.status_code == 422


def test_issue_key_shows_raw_key_once(client):
    client.post("/admin/tenants", json={"id": "demo-app", "name": "Demo"}, headers=ADMIN)
    r = client.post("/admin/tenants/demo-app/keys", headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["api_key"].startswith("dk_live_")
    assert client.post("/admin/tenants/ghost-app/keys", headers=ADMIN).status_code == 404


def test_revoke_key(client):
    client.post("/admin/tenants", json={"id": "demo-app", "name": "Demo"}, headers=ADMIN)
    key_id = client.post("/admin/tenants/demo-app/keys", headers=ADMIN).json()["key_id"]
    assert client.delete(f"/admin/keys/{key_id}", headers=ADMIN).status_code == 200
    assert client.delete("/admin/keys/key_missing", headers=ADMIN).status_code == 404