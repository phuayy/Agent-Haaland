"""P3/P4 exit. Low-severity path: file a ticket, close, nobody gets paged
(docs/01 state diagram: triaged_low -> closed)."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.agent.state import IncidentState
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.events import EventType


async def file_ticket_node(state: IncidentState, deps) -> dict:
    incident_id = state["incident_id"]
    classification = state["classification"]
    assert classification is not None

    ticket_ref = await deps.tickets.create_ticket(
        title=f"[{classification.severity}] {state['service_name']} — automated triage",
        description=classification.rationale,
        evidence={"service_name": state["service_name"], "repo_full_name": state["repo_full_name"]},
    )

    async with node_context(deps) as ctx:
        await ctx.incident_service.transition(
            incident_id,
            IncidentStatus.TRIAGED_LOW,
            actor_type=ActorType.SYSTEM,
            actor_label="file_ticket",
            summary=f"Filed ticket {ticket_ref} — {classification.severity}, no page",
            event_type=EventType.NOTIFICATION_SENT.value,
            payload={"ticket_ref": ticket_ref},
        )
        await ctx.incident_service.transition(
            incident_id,
            IncidentStatus.CLOSED,
            actor_type=ActorType.SYSTEM,
            actor_label="file_ticket",
            summary="Closed — low severity, handled via ticket",
            event_type=EventType.INCIDENT_CLOSED.value,
        )
        await ctx.incidents.set_root_cause(incident_id, classification.rationale)

    return {}
