ADMIN = {"Authorization": "Bearer test-admin-key"}
URL = "/v1/chat/completions"
BODY = {"model": "auto", "messages": [{"role": "user", "content": "hello world"}]}


def test_usage_requires_admin_key(client, auth):
    assert client.get("/admin/tenants/demo-app/usage").status_code == 401


def test_usage_unknown_tenant(client):
    assert client.get("/admin/tenants/ghost-app/usage", headers=ADMIN).status_code == 404


def test_usage_counts_per_tenant(client, make_auth):
    a = make_auth("tenant-a")
    make_auth("tenant-b")
    for _ in range(3):
        client.post(URL, json=BODY, headers=a)
    ua = client.get("/admin/tenants/tenant-a/usage", headers=ADMIN).json()
    ub = client.get("/admin/tenants/tenant-b/usage", headers=ADMIN).json()
    assert ua["requests"] == 3
    assert ub["requests"] == 0  # tenants never see each other's numbers