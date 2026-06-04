from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "local"
    api_base_url: str = "http://127.0.0.1:8000"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GRAPHVIEW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
