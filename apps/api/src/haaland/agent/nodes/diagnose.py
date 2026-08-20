"""Stage 2. Highest effort setting (docs/05). `supporting_evidence` has
min_length=1 on the schema — an unevidenced root cause is structurally
impossible to emit.

Two diagnosis paths, chosen at runtime:

- *agentic* (services/tool_loop_service.py): the model explores the
  workspace clone itself — grep, read_file, glob, list_dir, find_symbol —
  before committing to a root cause. Requires a tool-capable provider and
  HAALAND_AGENTIC_DIAGNOSIS_ENABLED (default on).
- *single-shot*: the pre-existing path — the model reasons only over the
  candidates locate_code ranked. Used when the provider isn't tool-capable
  (fake, openai), when the flag is off, or when no workspace exists.

Either way the same locate_code candidates seed the prompt: exploration
starts from ranked evidence, it doesn't replace the deterministic pass.
"""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.errors import AIRefusalError
from haaland.domain.events import EventType
from haaland.domain.models import Diagnosis
from haaland.llm.rendering import render_diagnosis_input
from haaland.services.code_toolbox import CodeToolbox


async def _run_diagnosis(state, deps, ctx, incident_id, bundle) -> Diagnosis:
    workspace_path = state.get("workspace_path")
    use_tool_loop = (
        ctx.tool_loop is not None
        and deps.settings.agentic_diagnosis_enabled
        and workspace_path is not None
    )
    if not use_tool_loop:
        return await ctx.llm_call.call(
            incident_id=incident_id,
            stage="diagnose",
            redacted_text=render_diagnosis_input(bundle),
            output_schema=Diagnosis,
        )

    workspace = deps.workspace.reopen(incident_id, workspace_path, state["base_sha"])
    outcome = await ctx.tool_loop.run(
        incident_id=incident_id,
        stage="diagnose",
        redacted_text=render_diagnosis_input(bundle),
        output_schema=Diagnosis,
        toolbox=CodeToolbox(workspace),
    )
    await ctx.audit.record(
        incident_id,
        EventType.AI_EXPLORED.value,
        actor_type=ActorType.AI,
        actor_label="diagnose",
        summary=(
            f"Explored workspace: {outcome.tool_calls} tool call(s) over "
            f"{outcome.turns} model turn(s)"
        ),
        payload={"tool_calls": outcome.tool_calls, "turns": outcome.turns},
    )
    return outcome.parsed


async def diagnose_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    bundle = state["evidence"]

    async with node_context(deps) as ctx:
        try:
            diagnosis = await _run_diagnosis(state, deps, ctx, incident_id, bundle)
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
