import pytest

from app.core.tenants import Store, TenantExists, TenantNotFound


def test_issue_and_resolve():
    s = Store()
    s.create_tenant("demo-app", "Demo")
    raw, rec = s.issue_key("demo-app")
    assert s.resolve(raw).id == "demo-app"
    assert raw not in repr(rec)  # only the hash is stored


def test_unknown_key_resolves_to_none():
    assert Store().resolve("dk_live_nope") is None


def test_revoked_key_stops_working():
    s = Store()
    s.create_tenant("demo-app", "Demo")
    raw, rec = s.issue_key("demo-app")
    assert s.revoke_key(rec.id) is True
    assert s.resolve(raw) is None


def test_inactive_tenant_cannot_authenticate():
    s = Store()
    t = s.create_tenant("demo-app", "Demo")
    raw, _ = s.issue_key("demo-app")
    t.active = False
    assert s.resolve(raw) is None


def test_duplicate_and_missing_tenant():
    s = Store()
    s.create_tenant("demo-app", "Demo")
    with pytest.raises(TenantExists):
        s.create_tenant("demo-app", "Again")
    with pytest.raises(TenantNotFound):
        s.issue_key("ghost-app")


def test_default_models_are_mock_only():
    t = Store().create_tenant("demo-app", "Demo")
    assert t.allows("auto") and not t.allows("gpt-4o-mini")