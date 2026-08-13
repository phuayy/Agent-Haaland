"""ARQ job bodies. The HTTP layer only ever enqueues; these run in the
worker process where a 20-second-plus LLM-and-git-clone workflow belongs
(docs/01)."""

from __future__ import annotations

from langgraph.types import Command

from haaland.logging import get_logger

logger = get_logger(__name__)


async def run_debug_session(ctx: dict, incident_id: str, initial_state: dict) -> None:
    graph = ctx["graph"]
    try:
        await graph.ainvoke(initial_state, config={"configurable": {"thread_id": incident_id}})
    except Exception:
        logger.exception("debug session run failed", incident_id=incident_id)
        raise


async def resume_debug_session(ctx: dict, incident_id: str, decision: dict) -> None:
    graph = ctx["graph"]
    try:
        await graph.ainvoke(
            Command(resume=decision), config={"configurable": {"thread_id": incident_id}}
        )
    except Exception:
        logger.exception("debug session resume failed", incident_id=incident_id)
        raise
