"""ARQ job bodies. The HTTP layer only ever enqueues; these run in the
worker process where a 20-second-plus LLM-and-git-clone workflow belongs
(docs/01)."""

from __future__ import annotations

import uuid

from langgraph.types import Command

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.errors import IllegalTransition
from haaland.domain.events import EventType
from haaland.logging import get_logger

logger = get_logger(__name__)


async def _mark_failed(deps, incident_id: str, exc: Exception) -> None:
    """Nodes only ever move an incident forward on their own success path
    (see escalate_manual.py for the one deliberate FAILED transition). An
    exception that escapes graph.ainvoke() means no node got a chance to
    record a terminal status, so without this the incident is stuck at
    whatever status its last checkpoint left it — forever, since arq does
    not auto-retry a plain exception. Best-effort: if FAILED somehow still
    isn't legal from wherever the crash landed, log and move on — the
    exception re-raised by the caller is what actually surfaces this to
    on-call/arq, this is just so the DB tells the same story."""
    try:
        async with node_context(deps) as ctx:
            await ctx.incident_service.transition(
                uuid.UUID(incident_id),
                IncidentStatus.FAILED,
                actor_type=ActorType.SYSTEM,
                actor_label="run_debug_session",
                summary=f"Unhandled error: {exc}",
                event_type=EventType.RUN_FAILED.value,
                payload={"error_type": type(exc).__name__, "detail": str(exc)},
            )
    except (IllegalTransition, LookupError):
        logger.warning("could not mark incident failed", incident_id=incident_id, exc_info=True)


async def run_debug_session(ctx: dict, incident_id: str, initial_state: dict) -> None:
    graph = ctx["graph"]
    try:
        await graph.ainvoke(initial_state, config={"configurable": {"thread_id": incident_id}})
    except Exception as exc:
        logger.exception("debug session run failed", incident_id=incident_id)
        await _mark_failed(ctx["deps"], incident_id, exc)
        raise


async def resume_debug_session(ctx: dict, incident_id: str, decision: dict) -> None:
    graph = ctx["graph"]
    try:
        await graph.ainvoke(
            Command(resume=decision), config={"configurable": {"thread_id": incident_id}}
        )
    except Exception as exc:
        logger.exception("debug session resume failed", incident_id=incident_id)
        await _mark_failed(ctx["deps"], incident_id, exc)
        raise
