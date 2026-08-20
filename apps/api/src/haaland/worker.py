"""ARQ worker entrypoint: `arq haaland.worker.WorkerSettings`. Builds the
same Deps + compiled graph the API process uses, so a job resumed here picks
up exactly where a checkpoint left off — including across a container
restart (docs/08 Phase 3's durability test)."""

from __future__ import annotations

from arq.connections import RedisSettings

from haaland.agent.checkpointer import build_checkpointer
from haaland.agent.graph import build_graph
from haaland.config import get_settings
from haaland.db.session import init_engine
from haaland.deps import build_deps
from haaland.logging import configure_logging, get_logger
from haaland.tasks.debug_session import resume_debug_session, run_debug_session

logger = get_logger(__name__)

_checkpointer_cm = None


async def startup(ctx: dict) -> None:
    global _checkpointer_cm
    settings = get_settings()
    configure_logging(json=settings.is_prod)
    init_engine(settings)

    deps = build_deps(settings)
    _checkpointer_cm = build_checkpointer(settings)
    checkpointer = await _checkpointer_cm.__aenter__()

    ctx["deps"] = deps
    ctx["graph"] = build_graph(deps, checkpointer)
    logger.info("worker startup complete")


async def shutdown(ctx: dict) -> None:
    if _checkpointer_cm is not None:
        await _checkpointer_cm.__aexit__(None, None, None)


class WorkerSettings:
    functions = [run_debug_session, resume_debug_session]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
    # arq's default job_timeout is 300s; a real run (clone + tool-loop
    # exploration + six LLM stages) routinely exceeds that, and a cancelled
    # job strands the incident mid-flight with no FAILED transition.
    job_timeout = get_settings().arq_job_timeout_seconds
    # A graph invocation is not idempotent (LLM spend, branch pushes,
    # notifications) — never let arq replay one automatically. Crash
    # handling is _mark_failed in tasks/debug_session.py, not a retry.
    max_tries = 1
