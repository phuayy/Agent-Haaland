"""Stage 2. Highest effort setting (docs/05). `supporting_evidence` has
min_length=1 on the schema — an unevidenced root cause is structurally
impossible to emit."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.errors import AIRefusalError
from haaland.domain.events import EventType
from haaland.domain.models import Diagnosis
from haaland.llm.rendering import render_diagnosis_input


async def diagnose_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    bundle = state["evidence"]

    async with node_context(deps) as ctx:
        try:
            diagnosis = await ctx.llm_call.call(
                incident_id=incident_id,
                stage="diagnose",
                redacted_text=render_diagnosis_input(bundle),
                output_schema=Diagnosis,
            )
        except AIRefusalError:
            await ctx.audit.record(
                incident_id,
                EventType.AI_REFUSED.value,
                actor_type=ActorType.AI,
                actor_label="diagnose",
                summary="Model refused the diagnosis request",
            )
            diagnosis = Diagnosis(
                root_cause="Diagnosis refused by the model; requires manual investigation.",
                category="unknown",
                confidence=0.0,
                culprit_locations=bundle.code_candidates[:1],
                supporting_evidence=[
                    {"evidence_id": "refused", "excerpt": "n/a", "why_relevant": "model refused"}
                ],
                recommended_strategy="manual_investigation",
                strategy_rationale="Model refused to diagnose.",
            )

        await ctx.incidents.set_root_cause(incident_id, diagnosis.root_cause)
        await ctx.incident_service.transition(
            incident_id,
            IncidentStatus.DIAGNOSING,
            actor_type=ActorType.AI,
            actor_label=deps.llm.name,
            summary=f"Diagnosed: {diagnosis.category} (confidence {diagnosis.confidence:.2f})",
            event_type=EventType.AI_DIAGNOSED.value,
            payload={"category": diagnosis.category, "confidence": diagnosis.confidence},
        )

    return {"diagnosis": diagnosis}
