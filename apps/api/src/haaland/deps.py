"""Process-wide DI container. Per-request/per-node objects that need a DB
session (repositories, and the services layered on top of them) are built
fresh inside a `session_scope()` block by whoever needs them — see
agent/nodes/_context.py — because a session must not outlive one unit of
work. Everything here is either stateless or holds its own connection pool
and is safe to share across the whole process."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from haaland.config import Settings, get_settings
from haaland.integrations.base import SandboxRunner, SCMProvider, TicketProvider
from haaland.llm.base import LLMProvider
from haaland.llm.budget import BudgetGuard
from haaland.llm.registry import build_provider
from haaland.redaction.service import Redactor
from haaland.redaction.vault import TokenVault
from haaland.services.check_service import CheckService
from haaland.services.code_search_service import CodeSearchService
from haaland.services.codeowners_service import CodeownersService
from haaland.services.notification_service import NotificationService
from haaland.services.postmortem_service import PostmortemService
from haaland.services.workspace_service import WorkspaceService


@dataclass
class Deps:
    settings: Settings
    redis: Redis
    vault: TokenVault
    redactor: Redactor
    llm: LLMProvider
    scm: SCMProvider
    sandbox: SandboxRunner
    tickets: TicketProvider
    budget: BudgetGuard

    workspace: WorkspaceService
    code_search: CodeSearchService
    check: CheckService
    codeowners: CodeownersService
    postmortem: PostmortemService
    notifications: NotificationService


_redis_singleton: Redis | None = None


def _redis_client(settings: Settings) -> Redis:
    global _redis_singleton
    if _redis_singleton is None:
        _redis_singleton = Redis.from_url(str(settings.redis_url), decode_responses=True)
    return _redis_singleton


def build_deps(settings: Settings | None = None) -> Deps:
    settings = settings or get_settings()
    redis = _redis_client(settings)
    vault = TokenVault(redis, settings.vault_encryption_key, settings.vault_ttl_hours)
    redactor = Redactor(vault)
    llm = build_provider(settings)
    budget = BudgetGuard(
        redis, per_incident_usd=settings.llm_max_usd_per_incident, per_day_usd=settings.llm_max_usd_per_day
    )

    from haaland.integrations.notify.registry import build_notifiers
    from haaland.integrations.scm.auth import build_credentials
    from haaland.integrations.scm.github import GitHubProvider
    from haaland.integrations.tickets.null import NullTicketProvider

    credentials = build_credentials(settings)
    scm = GitHubProvider(credentials)
    tickets = NullTicketProvider()

    if settings.env == "compose":
        from haaland.integrations.sandbox.docker_runner import DockerRunner

        sandbox: SandboxRunner = DockerRunner()
    else:
        from haaland.integrations.sandbox.subprocess_runner import SubprocessRunner

        sandbox = SubprocessRunner()

    return Deps(
        settings=settings,
        redis=redis,
        vault=vault,
        redactor=redactor,
        llm=llm,
        scm=scm,
        sandbox=sandbox,
        tickets=tickets,
        budget=budget,
        workspace=WorkspaceService(clone_token_provider=credentials.clone_token),
        code_search=CodeSearchService(),
        check=CheckService(sandbox, allow_unisolated_tests=settings.allow_host_test_execution),
        codeowners=CodeownersService(),
        postmortem=PostmortemService(),
        notifications=NotificationService(build_notifiers(settings)),
    )
