from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DWARPAL_", extra="ignore")

    app_env: str = "dev"
    mock_delay_ms: int = 0
    admin_key: str = ""  # empty = admin API disabled
    database_url: str = "sqlite:///./dwarpal.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()