"""Stage 2 (continued): rank candidate fixes and select one. On a retry
after a failed check, the previous failure's detail is fed back in so the
model treats it as authoritative rather than repeating the same mistake."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.agent.nodes._progress import announce_progress
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.events import EventType
from haaland.domain.models import FixEvaluation
from haaland.llm.rendering import render_evaluate_input


async def evaluate_fixes_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    diagnosis = state["diagnosis"]
    attempt = state.get("fix_attempt", 0) + 1

    # First attempt only. This node is re-entered on every failed check, on
    # every failed test run and on a human rejection — pinging each time
    # would turn one incident into five cards saying the same thing, which
    # is exactly how a bot gets muted. Retries are visible on the incident
    # timeline; the channel only needs to know the fix loop started.
    if attempt == 1:
        classification = state.get("classification")
        await announce_progress(
            state,
            deps,
            "fixing",
            severity=classification.severity if classification else None,
            detail=f"**Root cause:** {diagnosis.root_cause}",
        )

    async with node_context(deps) as ctx:
        incident = await ctx.incidents.get(incident_id)
        if incident is not None and incident.status == IncidentStatus.REJECTED.value:
            await ctx.incident_service.transition(
                incident_id,
                IncidentStatus.DIAGNOSING,
                actor_type=ActorType.SYSTEM,
                actor_label="evaluate_fixes",
                summary="Re-drafting after human rejection",
                event_type=EventType.AI_FIX_EVALUATED.value,
            )

        evaluation = await ctx.llm_call.call(
            incident_id=incident_id,
            stage="evaluate",
            redacted_text=render_evaluate_input(
                diagnosis, state.get("last_failure_detail"), attempt
            ),
            output_schema=FixEvaluation,
        )
        selected_summary = evaluation.candidates[evaluation.selected_index].summary
        await ctx.audit.record(
            incident_id,
            EventType.AI_FIX_EVALUATED.value,
            actor_type=ActorType.AI,
            actor_label=deps.llm.name,
            summary=f"Attempt {attempt}: selected '{selected_summary}'",
            payload={"attempt": attempt, "candidate_count": len(evaluation.candidates)},
        )

    return {"fix_evaluation": evaluation, "fix_attempt": attempt}
