"""12-factor settings. Fails fast at import time if a required value is missing."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HAALAND_", env_file=".env", extra="ignore")

    # Core
    env: Literal["dev", "test", "compose", "prod"] = "dev"
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://haaland:haaland@localhost:5432/haaland"
    )
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    app_base_url: str = "http://localhost:8000"
    secret_key: str = "dev-only-not-secure-change-me"
    vault_encryption_key: str = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # 32B b64, dev only

    # LLM
    llm_provider: Literal["fake", "anthropic", "openai"] = "fake"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    model_primary: str = "claude-opus-5"
    model_cheap: str = "claude-haiku-4-5"
    model_report: str = "claude-sonnet-5"
    llm_max_usd_per_incident: float = 2.00
    llm_max_usd_per_day: float = 50.00

    # GitHub
    github_token: str | None = None
    github_webhook_secret: str | None = None

    # Redaction
    redaction_engine: Literal["regex", "presidio"] = "regex"
    vault_ttl_hours: int = 24

    # Behaviour
    max_fix_attempts: int = 3
    approval_timeout_minutes: int = 30
    dedupe_window_seconds: int = 300

    # Alertmanager
    alertmanager_webhook_token: str | None = None

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
