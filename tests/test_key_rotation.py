import pytest
from helpers import ADMIN, Clock, chat, create_tenant, make_store

from app.core.tenants import KeyNotFound, KeyNotRotatable


def store_with_key():
    clock = Clock()
    store = make_store(clock)
    store.create_tenant("demo-app", "Demo")
    raw, rec = store.issue_key("demo-app")
    return clock, store, raw, rec


def test_old_key_works_during_overlap_then_expires():
    clock, store, old_raw, old = store_with_key()
    new_raw, _, _ = store.rotate_key(old.id, overlap_seconds=3600)
    assert store.resolve(old_raw).id == "demo-app" and store.resolve(new_raw).id == "demo-app"
    clock.advance(3599)
    assert store.resolve(old_raw) is not None
    clock.advance(2)
    assert store.resolve(old_raw) is None
    assert store.resolve(new_raw) is not None


def test_zero_overlap_is_an_immediate_cutover():
    _, store, old_raw, old = store_with_key()
    new_raw, _, _ = store.rotate_key(old.id, overlap_seconds=0)
    assert store.resolve(old_raw) is None and store.resolve(new_raw) is not None


def test_rotation_rules():
    _, store, _, old = store_with_key()
    _, new, _ = store.rotate_key(old.id, 60)
    with pytest.raises(KeyNotRotatable):
        store.rotate_key(old.id, 60)          # already rotated
    store.rotate_key(new.id, 60)              # the new key can be rotated again
    _, other = store.issue_key("demo-app")
    store.revoke_key(other.id)
    with pytest.raises(KeyNotRotatable):
        store.rotate_key(other.id, 60)        # revoked
    with pytest.raises(KeyNotFound):
        store.rotate_key("key_missing", 60)


def test_revoking_the_old_key_ends_the_overlap_early():
    _, store, old_raw, old = store_with_key()
    store.rotate_key(old.id, 3600)
    store.revoke_key(old.id)
    assert store.resolve(old_raw) is None


def test_list_keys_statuses():
    clock, store, _, old = store_with_key()
    _, new, _ = store.rotate_key(old.id, 60)
    status = {k["key_id"]: k["status"] for k in store.list_keys("demo-app")}
    assert status == {old.id: "expiring", new.id: "active"}
    clock.advance(61)
    assert {k["key_id"]: k["status"] for k in store.list_keys("demo-app")}[old.id] == "expired"
    store.revoke_key(new.id)
    assert {k["key_id"]: k["status"] for k in store.list_keys("demo-app")}[new.id] == "revoked"


def test_rotation_through_the_admin_api(client):
    headers = create_tenant(client)
    old_id = client.get("/admin/tenants/demo-app/keys", headers=ADMIN).json()["keys"][0]["key_id"]
    r = client.post(f"/admin/keys/{old_id}/rotate", json={"overlap_seconds": 3600}, headers=ADMIN)
    assert r.status_code == 201
    new_headers = {"Authorization": f"Bearer {r.json()['api_key']}"}
    assert chat(client, headers, "hi").status_code == 200       # old key, inside the window
    assert chat(client, new_headers, "hi").status_code == 200   # new key
    assert client.post(f"/admin/keys/{old_id}/rotate", headers=ADMIN).status_code == 409
    listing = client.get("/admin/tenants/demo-app/keys", headers=ADMIN)
    assert sorted(k["status"] for k in listing.json()["keys"]) == ["active", "expiring"]
    assert r.json()["api_key"] not in listing.text   # raw keys are never listed


def test_rotation_input_validation_and_auth(client):
    create_tenant(client)
    key_id = client.get("/admin/tenants/demo-app/keys", headers=ADMIN).json()["keys"][0]["key_id"]
    too_long = {"overlap_seconds": 8 * 24 * 3600}
    assert client.post(f"/admin/keys/{key_id}/rotate", json=too_long, headers=ADMIN).status_code == 422
    assert client.post(f"/admin/keys/{key_id}/rotate", json={"overlap_seconds": -1},
                       headers=ADMIN).status_code == 422
    assert client.post(f"/admin/keys/{key_id}/rotate").status_code == 401
    assert client.post("/admin/keys/key_missing/rotate", headers=ADMIN).status_code == 404
