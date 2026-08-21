"""P3/P4 exit. Low-severity path: file a ticket, notify, close (docs/01
state diagram: triaged_low -> closed).

Every severity band P1-P4 produces a notification. The low band still
carries no page and no human gate — it is a single informational card
naming the ticket, so a channel that only ever heard about P1/P2 no longer
silently drops the incidents the agent triaged away on its own."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.agent.state import IncidentState
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.events import EventType
from haaland.domain.models import NotificationMessage


async def file_ticket_node(state: IncidentState, deps) -> dict:
    incident_id = state["incident_id"]
    classification = state["classification"]
    assert classification is not None

    ticket_ref = await deps.tickets.create_ticket(
        title=f"[{classification.severity}] {state['service_name']} — automated triage",
        description=classification.rationale,
        evidence={"service_name": state["service_name"], "repo_full_name": state["repo_full_name"]},
    )

    message = NotificationMessage(
        kind="triaged_low",
        title=f"[{state['reference']}] Triaged {classification.severity} — ticket {ticket_ref}",
        body_markdown=(
            f"**Service:** {state['service_name']}\n"
            f"**Ticket:** {ticket_ref}\n"
            f"**Rationale:** {classification.rationale}\n\n"
            f"Low severity: filed and closed without a page. No review is required."
        ),
        incident_reference=state["reference"],
        severity=classification.severity,
        links={"Incident": f"{deps.settings.app_base_url}/incidents/{state['reference']}"},
    )
    # Delivery is best-effort by design (services/notification_service.py):
    # a Lark outage must not leave the incident stuck open in triaged_low.
    deliveries = await deps.notifications.broadcast(message)

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
        for delivery in deliveries:
            await ctx.notifications.record(
                incident_id=incident_id,
                channel=delivery.channel,
                target=delivery.channel,
                status=delivery.status,
                external_ref=delivery.external_ref,
                payload={"kind": message.kind, "detail": delivery.detail},
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
