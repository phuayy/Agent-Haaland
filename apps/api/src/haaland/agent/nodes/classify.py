from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.agent.state import IncidentState
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.errors import AIRefusalError
from haaland.domain.events import EventType
from haaland.domain.models import Classification
from haaland.llm.rendering import render_classify_input


async def classify_node(state: IncidentState, deps) -> dict:
    incident_id = state["incident_id"]
    bundle = state["evidence"]
    assert bundle is not None

    async with node_context(deps) as ctx:
        try:
            classification = await ctx.llm_call.call(
                incident_id=incident_id,
                stage="classify",
                redacted_text=render_classify_input(bundle),
                output_schema=Classification,
            )
        except AIRefusalError:
            await ctx.audit.record(
                incident_id,
                EventType.AI_REFUSED.value,
                actor_type=ActorType.AI,
                actor_label="classify",
                summary="Model refused the classification request",
            )
            classification = Classification(
                severity="P2",
                confidence=0.0,
                customer_impact="degraded",
                affected_services=[bundle.service_name],
                blast_radius_estimate="unknown — classification refused",
                rationale="Model refused; defaulting to P2 pending human review.",
                requires_immediate_page=True,
            )

        await ctx.incidents.set_severity(incident_id, classification.severity, classification.confidence)
        await ctx.incident_service.transition(
            incident_id,
            IncidentStatus.TRIAGING,
            actor_type=ActorType.AI,
            actor_label=deps.llm.name,
            summary=f"Classified {classification.severity} (confidence {classification.confidence:.2f})",
            event_type=EventType.AI_CLASSIFIED.value,
            payload=classification.model_dump(mode="json"),
        )

    return {"classification": classification}
