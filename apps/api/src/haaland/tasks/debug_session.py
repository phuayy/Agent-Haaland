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
from haaland.domain.models import NotificationMessage
from haaland.logging import get_logger

logger = get_logger(__name__)

# LangGraph's default recursion_limit is 25 super-steps. The happy path is
# ~15 nodes; each fix retry re-enters evaluate/apply/static (+tests), and a
# human rejection re-enters the whole drafting loop — a legitimate run at
# max_fix_attempts=3 plus one rejection exceeds 25. Sized so the ceiling
# catches genuine runaways only, never behaviour the routing allows.
_RECURSION_LIMIT = 100


def _graph_config(incident_id: str) -> dict:
    return {"configurable": {"thread_id": incident_id}, "recursion_limit": _RECURSION_LIMIT}


async def _notify_crash(deps, incident_id: str, reference: str, status: str, exc: Exception) -> None:
    """A crashed run is the one ending nobody is watching for. Every other
    terminal path posts a card from inside a node; this one has no node left
    alive to do it, so the notification is sent here or not at all.

    Wrapped in its own catch-all: the caller re-raises the original
    exception, and a notification channel throwing on the way out would
    replace the real cause of the failure with a Lark error."""
    try:
        message = NotificationMessage(
            kind="escalated",
            title=f"[{reference}] Run failed — agent stopped mid-incident",
            body_markdown=(
                f"**Failed at status:** {status}\n"
                f"**Error:** {type(exc).__name__}: {exc}\n\n"
                f"The automated run crashed and will not resume. "
                f"This incident needs a human."
            ),
            incident_reference=reference,
            links={"Incident": deps.settings.incident_url(reference)},
        )
        deliveries = await deps.notifications.broadcast(message)
        async with node_context(deps) as ctx:
            for delivery in deliveries:
                await ctx.notifications.record(
                    incident_id=uuid.UUID(incident_id),
                    channel=delivery.channel,
                    target=delivery.channel,
                    status=delivery.status,
                    external_ref=delivery.external_ref,
                    payload={"kind": message.kind, "detail": delivery.detail},
                )
    except Exception:  # noqa: BLE001 - never let the alerting path mask the crash
        logger.warning(
            "could not notify on failed run", incident_id=incident_id, exc_info=True
        )


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
    reference, status = incident_id, "unknown"
    try:
        async with node_context(deps) as ctx:
            # Read before the transition: the status the run died at is the
            # useful thing to page with, and set_status is about to overwrite it.
            incident = await ctx.incidents.get(uuid.UUID(incident_id))
            if incident is not None:
                reference, status = incident.reference, incident.status
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
    # Paged even when the transition above failed — the run is dead either
    # way, and a status the DB refused to write is more worth a human's
    # attention, not less.
    await _notify_crash(deps, incident_id, reference, status, exc)
    # A FAILED incident never resumes — its clone would otherwise sit on
    # disk until the container dies (workspaces are only ever cleaned by
    # generate_report on a completed run, or here on a crashed one).
    deps.workspace.cleanup(uuid.UUID(incident_id))


async def run_debug_session(ctx: dict, incident_id: str, initial_state: dict) -> None:
    graph = ctx["graph"]
    try:
        await graph.ainvoke(initial_state, config=_graph_config(incident_id))
    except Exception as exc:
        logger.exception("debug session run failed", incident_id=incident_id)
        await _mark_failed(ctx["deps"], incident_id, exc)
        raise


async def resume_debug_session(ctx: dict, incident_id: str, decision: dict) -> None:
    graph = ctx["graph"]
    try:
        await graph.ainvoke(Command(resume=decision), config=_graph_config(incident_id))
    except Exception as exc:
        logger.exception("debug session resume failed", incident_id=incident_id)
        await _mark_failed(ctx["deps"], incident_id, exc)
        raise
