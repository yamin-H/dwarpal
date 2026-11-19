import pytest

from app.core.store import Store
from app.core.tenants import TenantExists, TenantNotFound
from app.db.session import init_db, make_engine, make_session_factory


def make_store(url="sqlite://") -> Store:
    engine = make_engine(url)
    init_db(engine)
    return Store(make_session_factory(engine))


def test_issue_and_resolve():
    s = make_store()
    s.create_tenant("demo-app", "Demo")
    raw, rec = s.issue_key("demo-app")
    assert s.resolve(raw).id == "demo-app"
    assert raw not in repr(rec)


def test_unknown_key_resolves_to_none():
    assert make_store().resolve("dk_live_nope") is None


def test_revoked_key_stops_working():
    s = make_store()
    s.create_tenant("demo-app", "Demo")
    raw, rec = s.issue_key("demo-app")
    assert s.revoke_key(rec.id) is True
    assert s.resolve(raw) is None
    assert s.revoke_key("key_missing") is False


def test_inactive_tenant_cannot_authenticate():
    s = make_store()
    s.create_tenant("demo-app", "Demo")
    raw, _ = s.issue_key("demo-app")
    s.set_active("demo-app", False)
    assert s.resolve(raw) is None


def test_duplicate_and_missing_tenant():
    s = make_store()
    s.create_tenant("demo-app", "Demo")
    with pytest.raises(TenantExists):
        s.create_tenant("demo-app", "Again")
    with pytest.raises(TenantNotFound):
        s.issue_key("ghost-app")


def test_default_models_are_mock_only():
    t = make_store().create_tenant("demo-app", "Demo")
    assert t.allows("auto") and not t.allows("gpt-4o-mini")


def test_raw_key_is_never_stored():
    s = make_store()
    s.create_tenant("demo-app", "Demo")
    raw, _ = s.issue_key("demo-app")
    from app.db.models import ApiKeyRow

    with s._sf() as session:
        stored = [r.key_hash for r in session.query(ApiKeyRow).all()]
    assert raw not in stored


def test_data_survives_restart(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    first = make_store(url)
    first.create_tenant("demo-app", "Demo")
    raw, _ = first.issue_key("demo-app")
    second = make_store(url)  # simulates a server restart
    assert second.resolve(raw).id == "demo-app"