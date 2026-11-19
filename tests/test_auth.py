URL = "/v1/chat/completions"
BODY = {"model": "auto", "messages": [{"role": "user", "content": "hi"}]}
ADMIN = {"Authorization": "Bearer test-admin-key"}


def test_missing_key_is_401(client):
    r = client.post(URL, json=BODY)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "missing_api_key"


def test_invalid_key_is_401(client):
    r = client.post(URL, json=BODY, headers={"Authorization": "Bearer dk_live_fake"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_api_key"


def test_valid_key_works(client, auth):
    assert client.post(URL, json=BODY, headers=auth).status_code == 200


def test_revoked_key_stops_working(client):
    client.post("/admin/tenants", json={"id": "demo-app", "name": "d"}, headers=ADMIN)
    issued = client.post("/admin/tenants/demo-app/keys", headers=ADMIN).json()
    headers = {"Authorization": f"Bearer {issued['api_key']}"}
    assert client.post(URL, json=BODY, headers=headers).status_code == 200
    client.delete(f"/admin/keys/{issued['key_id']}", headers=ADMIN)
    assert client.post(URL, json=BODY, headers=headers).status_code == 401


def test_model_not_allowed_for_tenant(client, make_auth):
    headers = make_auth(models=["auto"])
    r = client.post(URL, json={**BODY, "model": "mock-echo"}, headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "model_not_allowed"


def test_health_stays_open(client):
    assert client.get("/healthz").status_code == 200