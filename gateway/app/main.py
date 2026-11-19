from dotenv import load_dotenv
from fastapi import FastAPI

from app.api import admin, chat, health
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.store import Store
from app.db.session import init_db, make_engine, make_session_factory

load_dotenv()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    app = FastAPI(title="Dwarpal", version="0.3.0")
    app.state.settings = settings
    app.state.store = Store(make_session_factory(engine))
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app