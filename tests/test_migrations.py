from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db.migrate import run_migrations
from app.db.models import Base
from app.db.session import make_engine


def engine_for(tmp_path):
    return make_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")


def test_fresh_database_matches_the_models(tmp_path):
    engine = engine_for(tmp_path)
    run_migrations(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"tenants", "api_keys", "usage", "alembic_version"} <= tables
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []  # migrations and models agree


def test_running_twice_is_harmless(tmp_path):
    engine = engine_for(tmp_path)
    run_migrations(engine)
    run_migrations(engine)


def test_upgrade_keeps_existing_data_and_applies_defaults(tmp_path):
    engine = engine_for(tmp_path)
    run_migrations(engine, "0001")  # the old schema
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO tenants (id, name, allowed_models, active, created_at) "
            "VALUES ('old-app', 'Old', '[\"auto\"]', 1, '2026-01-01 00:00:00.000000')"
        ))
        conn.execute(text(
            "INSERT INTO usage (tenant_id, model, provider, stream, status, prompt_tokens, "
            "completion_tokens, latency_ms, created_at) "
            "VALUES ('old-app', 'auto', 'mock', 0, 'ok', 1, 1, 5, '2026-01-01 00:00:00.000000')"
        ))
    run_migrations(engine)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT cache_enabled, allow_fallback, semantic_threshold FROM tenants"
        )).one()
        cost = conn.execute(text("SELECT cost_micros FROM usage")).scalar()
    assert tuple(row) == (1, 1, None) and cost == 0


def test_database_created_before_alembic_is_adopted(tmp_path):
    engine = engine_for(tmp_path)
    run_migrations(engine, "0001")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))  # looks like a Milestone 3-6 database
    run_migrations(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("tenants")}
    assert "cache_enabled" in columns