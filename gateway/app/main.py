from fastapi import FastAPI

from app.api import admin, chat, health
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.tenants import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Dwarpal", version="0.2.0")
    app.state.settings = settings or get_settings()
    app.state.store = Store()
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app


app = create_app()