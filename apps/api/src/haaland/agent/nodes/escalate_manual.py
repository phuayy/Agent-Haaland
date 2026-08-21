"""Reached when the diagnosis confidence is too low to draft a fix from, or
the bounded fix-attempt loop is exhausted. Drafting a confident-looking
patch from a weak diagnosis is worse than drafting nothing (docs/05) — this
node marks the incident failed-but-documented rather than shipping a guess.

It also pages: an escalation is the one outcome where the agent has stopped
working and a human has to pick the incident up, so it cannot wait for the
post-mortem card at the end of `generate_report` to say so in passing."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.events import EventType
from haaland.domain.models import NotificationMessage


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

    classification = state.get("classification")
    message = NotificationMessage(
        kind="escalated",
        title=f"[{state['reference']}] Escalated — automated remediation stopped",
        body_markdown=(
            f"**Service:** {state['service_name']}\n"
            f"**Reason:** {reason}\n"
            f"**Fix attempts:** {state.get('fix_attempt', 0)}\n\n"
            f"The agent stopped rather than ship a fix it could not stand behind. "
            f"This incident needs a human — no PR was opened."
        ),
        incident_reference=state["reference"],
        severity=classification.severity if classification else None,
        links={"Incident": f"{deps.settings.app_base_url}/incidents/{state['reference']}"},
    )
    deliveries = await deps.notifications.broadcast(message)

    async with node_context(deps) as ctx:
        for delivery in deliveries:
            await ctx.notifications.record(
                incident_id=incident_id,
                channel=delivery.channel,
                target=delivery.channel,
                status=delivery.status,
                external_ref=delivery.external_ref,
                payload={"kind": message.kind, "detail": delivery.detail},
            )

    return {}
