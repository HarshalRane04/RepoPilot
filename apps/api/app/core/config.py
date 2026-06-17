from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="local", alias="REPOPILOT_ENV")
    release_profile: str = Field(default="oss-demo", alias="REPOPILOT_RELEASE_PROFILE")
    api_host: str = Field(default="0.0.0.0", alias="REPOPILOT_API_HOST")
    api_port: int = Field(default=8000, alias="REPOPILOT_API_PORT")

    database_url: str = Field(
        default="postgresql+asyncpg://repopilot:repopilot@localhost:5432/repopilot",
        alias="DATABASE_URL",
    )
    alembic_database_url: str | None = Field(default=None, alias="ALEMBIC_DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND")

    github_webhook_secret: str = Field(default="change-me-local-dev", alias="GITHUB_WEBHOOK_SECRET")
    github_app_id: str | None = Field(default=None, alias="GITHUB_APP_ID")
    github_app_slug: str | None = Field(default=None, alias="GITHUB_APP_SLUG")
    github_client_id: str | None = Field(default=None, alias="GITHUB_CLIENT_ID")
    github_client_secret: str | None = Field(default=None, alias="GITHUB_CLIENT_SECRET")
    github_private_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GITHUB_APP_PRIVATE_KEY", "GITHUB_PRIVATE_KEY"),
    )
    github_private_key_path: str | None = Field(default=None, alias="GITHUB_PRIVATE_KEY_PATH")
    github_installation_id: str | None = Field(default=None, alias="GITHUB_INSTALLATION_ID")
    github_app_verified_at: str | None = Field(default=None, alias="GITHUB_APP_VERIFIED_AT")
    github_app_verified_installation_id: str | None = Field(default=None, alias="GITHUB_APP_VERIFIED_INSTALLATION_ID")
    github_write_smoke_verified_at: str | None = Field(default=None, alias="GITHUB_WRITE_SMOKE_VERIFIED_AT")
    github_oauth_callback_url: str = Field(
        default="http://localhost:8000/auth/github/callback",
        alias="GITHUB_OAUTH_CALLBACK_URL",
    )
    web_app_url: str = Field(default="http://localhost:3001", alias="WEB_APP_URL")
    github_api_base_url: str = Field(default="https://api.github.com", alias="GITHUB_API_BASE_URL")
    github_web_base_url: str = Field(default="https://github.com", alias="GITHUB_WEB_BASE_URL")
    github_writes_enabled: bool = Field(default=False, alias="GITHUB_WRITES_ENABLED")

    enable_queue_dispatch: bool = Field(default=True, alias="ENABLE_QUEUE_DISPATCH")
    dev_header_auth_enabled: bool = Field(default=False, alias="DEV_HEADER_AUTH_ENABLED")
    dev_auth_username: str = Field(default="local-owner", alias="DEV_AUTH_USERNAME")
    dev_auth_role: str = Field(default="owner", alias="DEV_AUTH_ROLE")
    session_secret_key: str = Field(default="change-me-session-secret", alias="SESSION_SECRET_KEY")
    runtime_secrets_key: str | None = Field(default=None, alias="REPOPILOT_RUNTIME_SECRETS_KEY")
    runtime_secrets_key_path: str = Field(
        default="~/.repopilot/runtime-secrets.key",
        alias="REPOPILOT_RUNTIME_SECRETS_KEY_PATH",
    )
    runtime_secrets_store_path: str = Field(
        default="~/.repopilot/runtime-secrets.json",
        alias="REPOPILOT_RUNTIME_SECRETS_STORE_PATH",
    )

    model_provider: str = Field(default="mock", alias="MODEL_PROVIDER")
    model_name: str = Field(default="mock-planner", alias="MODEL_NAME")
    model_api_key: str | None = Field(default=None, alias="MODEL_API_KEY")
    model_base_url: str | None = Field(default=None, alias="MODEL_BASE_URL")
    model_reasoning_level: str | None = Field(default=None, alias="MODEL_REASONING_LEVEL")
    model_provider_verified_at: str | None = Field(default=None, alias="MODEL_PROVIDER_VERIFIED_AT")
    model_provider_verified_model: str | None = Field(default=None, alias="MODEL_PROVIDER_VERIFIED_MODEL")
    model_request_timeout_seconds: int = Field(default=60, alias="MODEL_REQUEST_TIMEOUT_SECONDS")
    model_request_max_retries: int = Field(default=1, alias="MODEL_REQUEST_MAX_RETRIES")
    model_request_retry_backoff_seconds: float = Field(default=0.5, alias="MODEL_REQUEST_RETRY_BACKOFF_SECONDS")
    allow_model_fallback: bool = Field(default=False, alias="ALLOW_MODEL_FALLBACK")
    embedding_provider: str = Field(default="mock", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="mock-embedding", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1536, alias="EMBEDDING_DIMENSIONS")
    embedding_source_transfer_enabled: bool = Field(default=False, alias="EMBEDDING_SOURCE_TRANSFER_ENABLED")
    max_cost_per_run: float = Field(default=5.0, alias="REPOPILOT_MAX_COST_PER_RUN")
    max_tokens_per_run: int = Field(default=250_000, alias="REPOPILOT_MAX_TOKENS_PER_RUN")
    max_llm_calls_per_run: int = Field(default=40, alias="REPOPILOT_MAX_LLM_CALLS_PER_RUN")
    max_agent_retries: int = Field(default=3, alias="REPOPILOT_MAX_AGENT_RETRIES")
    rate_limit_window_seconds: int = Field(default=60, alias="REPOPILOT_RATE_LIMIT_WINDOW_SECONDS")
    rate_limit_state_changes_per_minute: int = Field(default=60, alias="REPOPILOT_RATE_LIMIT_STATE_CHANGES_PER_MINUTE")
    rate_limit_expensive_per_minute: int = Field(default=20, alias="REPOPILOT_RATE_LIMIT_EXPENSIVE_PER_MINUTE")

    repository_workspace_root: str = Field(default="/tmp/repopilot-repositories", alias="REPOPILOT_REPOSITORY_WORKSPACE_ROOT")
    sandbox_backend: str = Field(default="docker", alias="SANDBOX_BACKEND")
    sandbox_docker_image: str = Field(default="repopilot-sandbox:local", alias="SANDBOX_DOCKER_IMAGE")
    sandbox_memory_limit: str = Field(default="1g", alias="SANDBOX_MEMORY_LIMIT")
    sandbox_cpus: str = Field(default="1.0", alias="SANDBOX_CPUS")
    sandbox_pids_limit: int = Field(default=256, alias="SANDBOX_PIDS_LIMIT")
    workspace_cleanup_max_age_seconds: int = Field(default=86_400, alias="WORKSPACE_CLEANUP_MAX_AGE_SECONDS")
    workspace_cleanup_interval_seconds: int = Field(default=3_600, alias="WORKSPACE_CLEANUP_INTERVAL_SECONDS")
    artifact_store_root: str = Field(default="/tmp/repopilot-artifacts", alias="REPOPILOT_ARTIFACT_STORE_ROOT")
    artifact_inline_max_bytes: int = Field(default=12_000, alias="REPOPILOT_ARTIFACT_INLINE_MAX_BYTES")
    artifact_retention_max_age_seconds: int = Field(default=2_592_000, alias="REPOPILOT_ARTIFACT_RETENTION_MAX_AGE_SECONDS")
    artifact_retention_dry_run: bool = Field(default=True, alias="REPOPILOT_ARTIFACT_RETENTION_DRY_RUN")

    enable_otel: bool = Field(default=True, alias="ENABLE_OTEL")
    otel_exporter_otlp_endpoint: str | None = Field(default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    semgrep_enabled: bool = Field(default=False, alias="SEMGREP_ENABLED")
    codeql_enabled: bool = Field(default=False, alias="CODEQL_ENABLED")
    dependency_audit_enabled: bool = Field(default=False, alias="DEPENDENCY_AUDIT_ENABLED")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
