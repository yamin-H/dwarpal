from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DWARPAL_", extra="ignore")

    app_env: str = "dev"
    mock_delay_ms: int = 0
    admin_key: str = ""  # empty = admin API disabled
    database_url: str = "sqlite:///./dwarpal.db"
    redis_url: str = ""          # empty = cache disabled
    cache_ttl_seconds: int = 3600
    semantic_cache_enabled: bool = False
    qdrant_url: str = ""          # ":memory:" runs Qdrant in-process (dev only)
    qdrant_api_key: str = ""
    embedder: str = "sentence-transformers"   # or "hash" (dev only, not semantic)
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_prefix: str = "query:"
    semantic_threshold: float = 0.95    
    routing_config: str = ""
    log_level: str = "INFO"
    log_json: bool = True
    log_tracebacks: bool = False   # provider error messages can contain secrets


@lru_cache
def get_settings() -> Settings:
    return Settings()