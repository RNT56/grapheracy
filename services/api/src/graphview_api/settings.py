from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from graphview_api.action_policy import DEFAULT_SAFE_ACTION_TYPES


class Settings(BaseSettings):
    environment: str = Field(default="local", validation_alias=AliasChoices("GRAPHVIEW_ENVIRONMENT", "GRAPHVIEW_ENV"))
    api_base_url: str = "http://127.0.0.1:8000"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    database_url: str = "sqlite:///./.graphview/graphview.sqlite"
    arq_redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias=AliasChoices("ARQ_REDIS_URL", "GRAPHVIEW_ARQ_REDIS_URL"),
    )
    secret_key: str = "local-dev-graphview-secret"
    oidc_issuer_url: str | None = None
    oidc_backchannel_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_audience: str | None = None
    oidc_redirect_uri: str = "http://127.0.0.1:8000/api/v1/auth/callback"
    oidc_scopes: str = "openid profile email"
    oidc_groups_claim: str = "groups"
    oidc_reader_group: str = "graphview-readers"
    oidc_reviewer_group: str = "graphview-reviewers"
    oidc_admin_group: str = "graphview-admins"
    oidc_service_group: str = "graphview-services"
    oidc_project_group_prefix: str = "graphview-project:"
    session_cookie_name: str = "graphview_session"
    session_ttl_seconds: int = 28_800
    session_secure_cookie: bool = True
    secret_provider: str = "local-aead"
    vault_address: str | None = None
    vault_token: str | None = None
    vault_token_file: str | None = None
    vault_mount: str = "secret"
    vault_namespace: str | None = None
    object_store_provider: str = "local"
    object_store_path: str = "./.graphview/objects"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "graphview"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    upload_max_bytes: int = 100_000_000
    malware_scan_url: str | None = None
    malware_scan_clamd_host: str | None = None
    malware_scan_clamd_port: int = 3310
    outbound_allowed_hosts: str = ""
    github_api_url: str = "https://api.github.com"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_from_address: str | None = None
    smtp_suppressed_recipients: str = ""
    action_webhook_allowed_hosts: str = ""
    rate_limit_window_seconds: int = 60
    rate_limit_requests: int = 600
    rate_limit_mutations: int = 120
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "graphview-api"
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
    agent_context_max_blob_bytes: int = 512_000
    agent_context_retention_days: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GRAPHVIEW_",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.environment in {"local", "test", "development"}:
            return self
        missing = [
            name
            for name, value in {
                "oidc_issuer_url": self.oidc_issuer_url,
                "oidc_client_id": self.oidc_client_id,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Production identity settings are required: {', '.join(missing)}")
        if self.database_url.startswith("sqlite"):
            raise ValueError("SQLite is a development-only adapter")
        if self.secret_key == "local-dev-graphview-secret" or len(self.secret_key) < 32:
            raise ValueError("A strong non-default GRAPHVIEW_SECRET_KEY is required")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are forbidden outside development")
        if self.secret_provider != "vault" or not self.vault_address:
            raise ValueError("Production requires GRAPHVIEW_SECRET_PROVIDER=vault and GRAPHVIEW_VAULT_ADDRESS")
        if not self.vault_token and not self.vault_token_file:
            raise ValueError("Vault authentication requires a token or mounted token file")
        if self.object_store_provider != "s3" or not self.s3_endpoint_url:
            raise ValueError("Production requires an S3-compatible object store")
        if not self.s3_access_key_id or not self.s3_secret_access_key:
            raise ValueError("S3 credentials must be injected from the external secret provider")
        if not self.malware_scan_url and not self.malware_scan_clamd_host:
            raise ValueError("Production uploads require a malware scan hook")
        if not self.outbound_allowed_hosts.strip():
            raise ValueError("Production requires GRAPHVIEW_OUTBOUND_ALLOWED_HOSTS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
