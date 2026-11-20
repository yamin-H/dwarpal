from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
LOCK_ID = 727202601


def run_migrations(engine: Engine, revision: str = "head") -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # Two replicas starting together must not migrate at the same time.
            conn.execute(text(f"SELECT pg_advisory_xact_lock({LOCK_ID})"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)