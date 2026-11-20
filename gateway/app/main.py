import logging

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI

from app.api import admin, chat, health
from app.api import metrics as metrics_api
from app.cache.exact import NullCache, RedisCache
from app.cache.factory import build_semantic_cache
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.pricing import load_price_table, validate_routing_prices
from app.core.store import Store
from app.db.migrate import run_migrations
from app.db.session import init_db, is_memory_sqlite, make_engine, make_session_factory
from app.observability.logging import configure_logging
from app.observability.metrics import Metrics
from app.observability.middleware import RequestContextMiddleware
from app.routing.providers import get_provider
from app.routing.router import Router, load_routing_config

load_dotenv()


def create_app(
    settings: Settings | None = None, cache=None, semantic=None, router=None, metrics=None,
    prices=None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.log_tracebacks)
    engine = make_engine(settings.database_url)
    if is_memory_sqlite(settings.database_url):
        init_db(engine)                      # tests: throwaway in-memory database
    elif settings.auto_migrate:
        run_migrations(engine)
        logging.getLogger("dwarpal").info("database migrations applied")
    if cache is None:
        if settings.redis_url:
            client = aioredis.from_url(
                settings.redis_url, decode_responses=True,
                socket_connect_timeout=1, socket_timeout=2,
            )
            cache = RedisCache(client, settings.cache_ttl_seconds)
        else:
            cache = NullCache()
    prices = prices or load_price_table(settings.prices_config)
    metrics = metrics or Metrics()
    if router is None:
        routing = load_routing_config(settings.routing_config)
        validate_routing_prices(routing.chains, prices)  # fail fast: no unpriced fallbacks
        router = Router(lambda model: get_provider(model, settings), routing, metrics=metrics)
    metrics.bind_router(router)

    app = FastAPI(title="Dwarpal", version="0.7.0")
    app.state.settings = settings
    app.state.store = Store(make_session_factory(engine))
    app.state.cache = cache
    app.state.semantic = semantic if semantic is not None else build_semantic_cache(settings)
    app.state.router = router
    app.state.metrics = metrics
    app.state.prices = prices
    app.add_middleware(RequestContextMiddleware, metrics=metrics)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(metrics_api.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app