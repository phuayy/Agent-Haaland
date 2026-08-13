"""Reached when the diagnosis confidence is too low to draft a fix from, or
the bounded fix-attempt loop is exhausted. Drafting a confident-looking
patch from a weak diagnosis is worse than drafting nothing (docs/05) — this
node marks the incident failed-but-documented rather than shipping a guess."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.events import EventType


async def escalate_manual_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    reason = state.get("last_failure_detail") or "diagnosis confidence too low for automated remediation"

    async with node_context(deps) as ctx:
        await ctx.incident_service.transition(
            incident_id,
            IncidentStatus.FAILED,
            actor_type=ActorType.SYSTEM,
            actor_label="escalate_manual",
            summary=f"Escalated to manual investigation: {reason}",
            event_type=EventType.FIX_ATTEMPT_EXHAUSTED.value,
            payload={"fix_attempt": state.get("fix_attempt", 0), "reason": reason},
        )

    return {}
