import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADMIN_KEY = "test-admin-key"
ADMIN = {"Authorization": f"Bearer {ADMIN_KEY}"}


@pytest.fixture
def client():
    return TestClient(create_app(Settings(admin_key=ADMIN_KEY, _env_file=None)))


@pytest.fixture
def make_auth(client):
    def _make(tenant_id="demo-app", models=None):
        body = {"id": tenant_id, "name": tenant_id}
        if models is not None:
            body["allowed_models"] = models
        client.post("/admin/tenants", json=body, headers=ADMIN)
        key = client.post(f"/admin/tenants/{tenant_id}/keys", headers=ADMIN).json()["api_key"]
        return {"Authorization": f"Bearer {key}"}

    return _make


@pytest.fixture
def auth(make_auth):
    return make_auth()