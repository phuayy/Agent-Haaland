"""12-factor settings. Fails fast at startup if a required value is missing
or a dev-only default would ship to production."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET_KEY = "dev-only-not-secure-change-me"
_DEV_VAULT_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # 32B b64, dev only


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HAALAND_", env_file=".env", extra="ignore")

    # Core
    env: Literal["dev", "test", "compose", "prod"] = "dev"
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://haaland:haaland@localhost:5432/haaland"
    )
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    app_base_url: str = "http://localhost:8000"
    secret_key: str = _DEV_SECRET_KEY
    vault_encryption_key: str = _DEV_VAULT_KEY
    cors_origins: str = "*"  # comma-separated; "*" is dev-only convenience

    # LLM
    llm_provider: Literal["fake", "anthropic", "openai"] = "fake"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    model_primary: str = "claude-opus-5"
    model_cheap: str = "claude-haiku-4-5"
    model_report: str = "claude-sonnet-5"
    llm_max_usd_per_incident: float = 2.00
    llm_max_usd_per_day: float = 50.00

    # GitHub — `app` is the production mode (least-privilege, revocable,
    # short-lived installation tokens); `pat` is the single-dev fallback.
    github_auth_mode: Literal["pat", "app"] = "pat"
    github_token: str | None = None
    github_app_id: str | None = None
    github_app_private_key: str | None = None  # PEM contents, inline
    github_app_private_key_path: Path | None = None  # or a path to the .pem
    github_app_installation_id: int | None = None
    github_webhook_secret: str | None = None

    # Notifications — comma-separated channel names, e.g. "lark" or "lark,slack"
    notify_channels: str = ""
    lark_webhook_url: str | None = None
    lark_webhook_secret: str | None = None  # only if the bot has signature verification on

    # Redaction
    redaction_engine: Literal["regex", "presidio"] = "regex"
    vault_ttl_hours: int = 24

    # Behaviour
    max_fix_attempts: int = 3
    approval_timeout_minutes: int = 30
    dedupe_window_seconds: int = 300
    # SubprocessRunner executes the target repo's tests (i.e. code the model
    # just wrote) directly on the host. That needs an explicit opt-in; the
    # DockerRunner sandbox never does.
    allow_host_test_execution: bool = False

    # Alertmanager
    alertmanager_webhook_token: str | None = None

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def notify_channel_list(self) -> list[str]:
        return [c.strip().lower() for c in self.notify_channels.split(",") if c.strip()]

    @model_validator(mode="after")
    def _no_dev_secrets_in_prod(self) -> Settings:
        if self.env == "prod":
            problems = []
            if self.secret_key == _DEV_SECRET_KEY:
                problems.append("HAALAND_SECRET_KEY is still the dev default")
            if self.vault_encryption_key == _DEV_VAULT_KEY:
                problems.append("HAALAND_VAULT_ENCRYPTION_KEY is still the dev default")
            if self.cors_origins == "*":
                problems.append("HAALAND_CORS_ORIGINS must not be '*' in prod")
            if problems:
                raise ValueError("refusing to start in prod: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
