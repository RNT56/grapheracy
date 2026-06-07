from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from graphview_api.action_policy import DEFAULT_SAFE_ACTION_TYPES


class Settings(BaseSettings):
    environment: str = Field(default="local", validation_alias=AliasChoices("GRAPHVIEW_ENVIRONMENT", "GRAPHVIEW_ENV"))
    api_base_url: str = "http://127.0.0.1:8000"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    database_url: str = "sqlite:///./.graphview/graphview.sqlite"
    secret_key: str = "local-dev-graphview-secret"
    llm_enabled: bool = False
    llm_provider: str = "openai-compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4.1-mini"
    auto_commit_threshold: float = 0.92
    ai_default_provider: str = "graphview-local"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.5"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-opus-4.8"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_model: str = "gemini-3.1-pro"
    safe_action_types: str = ",".join(DEFAULT_SAFE_ACTION_TYPES)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GRAPHVIEW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
