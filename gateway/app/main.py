import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI
from app.routing.providers import get_provider
from app.routing.router import Router, load_routing_config
from app.api import admin, chat, health
from app.cache.exact import NullCache, RedisCache
from app.cache.factory import build_semantic_cache
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.store import Store
from app.db.session import init_db, make_engine, make_session_factory

load_dotenv()


def create_app(settings: Settings | None = None, cache=None, semantic=None, router=None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    if cache is None:
        if settings.redis_url:
            client = aioredis.from_url(
                settings.redis_url, decode_responses=True,
                socket_connect_timeout=1, socket_timeout=2,
            )
            cache = RedisCache(client, settings.cache_ttl_seconds)
        else:
            cache = NullCache()
    app = FastAPI(title="Dwarpal", version="0.4.0")
    app.state.settings = settings
    app.state.store = Store(make_session_factory(engine))
    app.state.cache = cache
    app.state.semantic = semantic if semantic is not None else build_semantic_cache(settings)
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    app.state.router = router or Router(
        lambda model: get_provider(model, settings), load_routing_config(settings.routing_config)
    )


    return app