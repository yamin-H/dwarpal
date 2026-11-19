from sqlalchemy import inspect

from app.db.session import init_db, make_engine


def test_tables_are_created():
    engine = make_engine("sqlite://")
    init_db(engine)
    assert {"tenants", "api_keys", "usage"} <= set(inspect(engine).get_table_names())