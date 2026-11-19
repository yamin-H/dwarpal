from fastapi import FastAPI

from app.api import chat, health
from app.core.errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="Dwarpal", version="0.1.0")
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(chat.router)
    return app


app = create_app()