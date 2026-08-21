"""12-factor settings. Fails fast at startup if a required value is missing
or a dev-only default would ship to production."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator, model_validator
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
    # Origin of the Next.js dashboard (apps/web), which is a different service
    # from this API even when a single reverse proxy fronts both. Notification
    # buttons point at dashboard pages, not API routes, so they must not be
    # built from app_base_url: /incidents/{reference} exists only in the web
    # app, and resolving it against the API origin returns 404 Not Found.
    # Unset falls back to app_base_url for the single-origin dev setup.
    dashboard_base_url: str | None = None
    secret_key: str = _DEV_SECRET_KEY
    vault_encryption_key: str = _DEV_VAULT_KEY
    cors_origins: str = "*"  # comma-separated; "*" is dev-only convenience
    # Bearer token every /api/* route requires (webhooks carry their own
    # HMAC/bearer verification instead). Unset = open, a dev-only
    # convenience — prod refuses to start without it, same as the other
    # dev defaults below.
    api_auth_token: str | None = None

    # LLM — model_* names are provider-specific strings; they must match the
    # vocabulary of whichever llm_provider is selected (e.g. deepseek-v4-flash
    # for deepseek, claude-opus-5 for anthropic).
    llm_provider: Literal["fake", "deepseek", "anthropic", "openai"] = "fake"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None
    # Override only to point at a proxy or the self-hosted OpenAI-compatible
    # gateway; the Anthropic-compatible surface (/anthropic) is NOT usable here
    # — see llm/providers/deepseek.py for why.
    deepseek_base_url: str = "https://api.deepseek.com"
    # Thinking mode on the structured (deliverable) DeepSeek calls —
    # `extra_body={"thinking": {"type": "enabled"}}`. On by default: root-cause
    # quality is what this pipeline is judged on and it comes from the reasoning
    # pass. Exploration turns are unaffected — function calling and thinking are
    # mutually exclusive on DeepSeek, see llm/providers/deepseek.py.
    deepseek_thinking: bool = True
    model_primary: str = "deepseek-v4-flash"
    model_cheap: str = "deepseek-v4-flash"
    model_report: str = "deepseek-v4-pro"
    llm_max_usd_per_incident: float = 2.00
    llm_max_usd_per_day: float = 50.00
    # Agentic exploration — the read/grep tool loop the diagnose stage runs
    # over the workspace clone (services/tool_loop_service.py). Providers that
    # aren't tool-capable (fake, openai) fall back to single-shot diagnosis
    # regardless of this flag, so it is inert in offline/CI runs.
    agentic_diagnosis_enabled: bool = True
    tool_loop_max_iterations: int = Field(default=12, ge=1, le=50)
    # Turn budget when locate_code found zero candidates and the loop must
    # localize from scratch (cold start) — needs more than "a handful".
    tool_loop_cold_start_max_iterations: int = Field(default=24, ge=1, le=50)

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
    # Short "still working" cards at the three in-flight milestones (accepted,
    # diagnosing, debugging) on top of the outcome cards the graph already
    # sends. On by default: a real run takes minutes, and without them the
    # first thing a chat hears about an incident is a PR review request for
    # something it never saw start. Set false for a channel that only wants
    # outcomes. See services/progress_service.py.
    notify_progress: bool = True
    # Lark transport. `webhook` is a per-chat custom bot (no org onboarding,
    # push-only). `app` is an internal application installed into the Lark
    # tenant: any chat or person the app can reach, editable cards, and the
    # prerequisite for interactive approvals (docs/11 §4, docs/13).
    lark_mode: Literal["webhook", "app"] = "webhook"
    lark_domain: Literal["global", "feishu"] = "global"  # larksuite.com vs feishu.cn
    # mode=webhook
    lark_webhook_url: str | None = None
    lark_webhook_secret: str | None = None  # only if the bot has signature verification on
    # mode=app
    lark_app_id: str | None = None
    lark_app_secret: str | None = None
    lark_default_receive_id: str | None = None  # chat_id (oc_…), open_id (ou_…) or email
    lark_default_receive_id_type: Literal["chat_id", "open_id", "user_id", "union_id", "email"] = (
        "chat_id"
    )
    # Inbound card callbacks / events (POST /webhooks/lark/card)
    lark_encrypt_key: str | None = None
    lark_verification_token: str | None = None

    # Redaction
    redaction_engine: Literal["regex", "presidio"] = "regex"
    vault_ttl_hours: int = 24

    # Behaviour
    # Severity bands that take the low-severity exit (file a ticket, close,
    # no code touched). Empty — the default — means every band P1-P4 runs the
    # full debug loop: clone, diagnose, patch, branch, push, PR, approval
    # gate. Set e.g. "P3,P4" to restore the ticket-only shortcut for the
    # cheap bands when the LLM/CI budget matters more than coverage.
    ticket_only_severities: str = ""
    max_fix_attempts: int = 3
    approval_timeout_minutes: int = 30
    dedupe_window_seconds: int = 300
    # SubprocessRunner executes the target repo's tests (i.e. code the model
    # just wrote) directly on the host. That needs an explicit opt-in; the
    # DockerRunner sandbox never does.
    allow_host_test_execution: bool = False

    # Alertmanager
    alertmanager_webhook_token: str | None = None

    # Worker — ceiling for one debug-session job. The default arq timeout is
    # 300s, which a real run (clone + tool-loop exploration + six LLM stages)
    # exceeds routinely; a cancelled job strands the incident mid-flight.
    arq_job_timeout_seconds: int = Field(default=1800, ge=60)

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_scheme(cls, value: object) -> object:
        """Managed platforms (Render, Heroku) inject `postgres://` or
        `postgresql://` URLs. SQLAlchemy 2 dropped the former and resolves
        the latter to psycopg2, which is not installed — the only driver
        this app ships for the runtime engine is asyncpg. Rewrite the bare
        schemes instead of failing at first connect; explicit `+driver`
        URLs pass through untouched."""
        if isinstance(value, str):
            if value.startswith("postgres://"):
                value = "postgresql://" + value.removeprefix("postgres://")
            if value.startswith("postgresql://"):
                value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        return value

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def dashboard_url(self) -> str:
        """Base for every user-facing link in a notification. Trailing slashes
        are stripped so the callers can keep concatenating `/incidents/...`."""
        return (self.dashboard_base_url or self.app_base_url).rstrip("/")

    def incident_url(self, reference: str) -> str:
        """The one place that knows the dashboard's incident route. Every
        notification link goes through here so a future route rename is a
        single edit rather than a hunt through the graph nodes."""
        return f"{self.dashboard_url}/incidents/{reference}"

    @property
    def ticket_only_severity_set(self) -> frozenset[str]:
        """Parsed `ticket_only_severities`, upper-cased. Routing asks this,
        never the raw string, so "p3, P4" and "P3,P4" behave the same."""
        return frozenset(s.strip().upper() for s in self.ticket_only_severities.split(",") if s.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def notify_channel_list(self) -> list[str]:
        return [c.strip().lower() for c in self.notify_channels.split(",") if c.strip()]

    @model_validator(mode="after")
    def _models_match_provider(self) -> Settings:
        """The model_* defaults track the default provider (deepseek). Switching
        HAALAND_LLM_PROVIDER without also switching the model names is a silent
        404-at-first-incident, so catch it at startup instead."""
        expected_prefix = {"deepseek": "deepseek-", "anthropic": "claude-", "openai": "gpt-"}.get(
            self.llm_provider
        )
        if expected_prefix:
            wrong = [
                f"{name}={value!r}"
                for name, value in (
                    ("HAALAND_MODEL_PRIMARY", self.model_primary),
                    ("HAALAND_MODEL_CHEAP", self.model_cheap),
                    ("HAALAND_MODEL_REPORT", self.model_report),
                )
                if not value.startswith(expected_prefix)
            ]
            if wrong:
                raise ValueError(
                    f"llm_provider={self.llm_provider!r} expects model names starting with "
                    f"{expected_prefix!r}; got " + ", ".join(wrong)
                )
        return self

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
            if not self.api_auth_token:
                problems.append(
                    "HAALAND_API_AUTH_TOKEN is unset — the /api routes (including "
                    "the approval gate) must not be open on a public URL"
                )
            if problems:
                raise ValueError("refusing to start in prod: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
