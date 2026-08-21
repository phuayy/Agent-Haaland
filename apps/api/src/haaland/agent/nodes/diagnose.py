"""Stage 2. Highest effort setting (docs/05). `supporting_evidence` has
min_length=1 on the schema — an unevidenced root cause is structurally
impossible to emit.

Two diagnosis paths, chosen at runtime:

- *agentic* (services/tool_loop_service.py): the model explores the
  workspace clone itself — grep, read_file, glob, list_dir, find_symbol —
  before committing to a root cause. Requires a tool-capable provider and
  HAALAND_AGENTIC_DIAGNOSIS_ENABLED (default on). When locate_code found
  zero candidates the loop runs in *cold-start* mode: a different system
  block that makes localization explicitly the model's job, a deterministic
  orientation seed (repo tree, manifests, entrypoints) so turn 1 isn't
  spent on `list_dir .`, and a larger turn budget.
- *single-shot*: the pre-existing path — the model reasons only over the
  candidates locate_code ranked. Used when the provider isn't tool-capable
  (fake, openai), when the flag is off, or when no workspace exists.

The model emits a DiagnosisDraft — culprit locations as path+span refs only,
no snippets — and this node hydrates them from the clone into the Diagnosis
the rest of the graph consumes. A ref that doesn't resolve in the clone is a
detectable hallucination and is dropped (and audited), never invented.
"""

from __future__ import annotations

from haaland.agent.nodes._context import node_context, workspace_from_state
from haaland.agent.nodes._progress import announce_progress
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.errors import AIInvalidOutputError, AIRefusalError
from haaland.domain.events import EventType
from haaland.domain.models import (
    CodeLocation,
    CulpritLocationRef,
    Diagnosis,
    DiagnosisDraft,
    EvidenceBundle,
)
from haaland.llm.rendering import render_diagnosis_input
from haaland.services.code_toolbox import CodeToolbox, orientation_seed
from haaland.services.workspace_service import Workspace

_MAX_SNIPPET_LINES = 80


def _hydrate_culprits(
    refs: list[CulpritLocationRef],
    workspace: Workspace | None,
    bundle: EvidenceBundle,
) -> tuple[list[CodeLocation], list[str]]:
    """Model refs (path + span) -> full CodeLocations with the snippet read
    server-side. Falls back to a matching locate_code candidate when there is
    no workspace; returns (hydrated, unresolved_paths)."""
    hydrated: list[CodeLocation] = []
    unresolved: list[str] = []
    for ref in refs:
        start = min(ref.start_line, ref.end_line)
        end = min(max(ref.start_line, ref.end_line), start + _MAX_SNIPPET_LINES)
        content = workspace.read_file(ref.path) if workspace is not None else None
        if content is not None:
            lines = content.splitlines()
            if start > len(lines):
                unresolved.append(f"{ref.path}:{start}-{end} (past end of file)")
                continue
            snippet = "\n".join(lines[start - 1 : min(len(lines), end)])
            hydrated.append(
                CodeLocation(
                    path=ref.path,
                    start_line=start,
                    end_line=min(end, len(lines)),
                    snippet=snippet,
                    reason="model_identified",
                    confidence=0.5,
                )
            )
            continue
        # No workspace (or unreadable path): accept only what the
        # deterministic pass already located.
        match = next((c for c in bundle.code_candidates if c.path == ref.path), None)
        if match is not None:
            hydrated.append(match)
        else:
            unresolved.append(f"{ref.path}:{start}-{end}")
    return hydrated, unresolved


def _finalize(
    draft: DiagnosisDraft, workspace: Workspace | None, bundle: EvidenceBundle
) -> tuple[Diagnosis, list[str]]:
    culprits, unresolved = _hydrate_culprits(draft.culprit_locations, workspace, bundle)
    diagnosis = Diagnosis(
        **draft.model_dump(exclude={"culprit_locations"}),
        culprit_locations=culprits,
    )
    return diagnosis, unresolved


async def _run_diagnosis(state, deps, ctx, incident_id, bundle) -> tuple[Diagnosis, list[str]]:
    workspace_path = state.get("workspace_path")
    use_tool_loop = (
        ctx.tool_loop is not None
        and deps.settings.agentic_diagnosis_enabled
        and workspace_path is not None
    )
    if not use_tool_loop:
        workspace = (
            await workspace_from_state(deps, state) if workspace_path is not None else None
        )
        draft = await ctx.llm_call.call(
            incident_id=incident_id,
            stage="diagnose",
            redacted_text=render_diagnosis_input(bundle),
            output_schema=DiagnosisDraft,
        )
        return _finalize(draft, workspace, bundle)

    workspace = await workspace_from_state(deps, state)
    cold_start = not bundle.code_candidates
    orientation = None
    max_iterations = None
    if cold_start:
        # Deterministic seed, but redacted first — it is workspace content,
        # and the redaction choke point covers everything the model sees.
        seed = await deps.redactor.redact_text(incident_id, orientation_seed(workspace))
        orientation = seed.text
        max_iterations = deps.settings.tool_loop_cold_start_max_iterations

    outcome = await ctx.tool_loop.run(
        incident_id=incident_id,
        stage="diagnose",
        redacted_text=render_diagnosis_input(bundle, orientation=orientation),
        output_schema=DiagnosisDraft,
        toolbox=CodeToolbox(workspace),
        cold_start=cold_start,
        max_iterations=max_iterations,
    )
    await ctx.audit.record(
        incident_id,
        EventType.AI_EXPLORED.value,
        actor_type=ActorType.AI,
        actor_label="diagnose",
        summary=(
            f"Explored workspace: {outcome.tool_calls} tool call(s) over "
            f"{outcome.turns} model turn(s)"
            + (" [cold start — no pre-located candidates]" if cold_start else "")
        ),
        payload={
            "tool_calls": outcome.tool_calls,
            "turns": outcome.turns,
            "cold_start": cold_start,
        },
    )
    return _finalize(outcome.parsed, workspace, bundle)


def _fallback_diagnosis(bundle: EvidenceBundle, reason: str) -> Diagnosis:
    return Diagnosis(
        root_cause=f"{reason}; requires manual investigation.",
        category="unknown",
        confidence=0.0,
        culprit_locations=bundle.code_candidates[:1],
        supporting_evidence=[
            {"evidence_id": "unavailable", "excerpt": "n/a", "why_relevant": reason}
        ],
        recommended_strategy="manual_investigation",
        strategy_rationale=f"{reason}.",
    )


async def diagnose_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    bundle = state["evidence"]

    # Announced before the model runs, not after: the tool loop is the
    # longest silence in the pipeline, and the point of the ping is to
    # cover it. The severity comes from classify, so this card doubles as
    # the channel's first sight of the band the incident was triaged into.
    classification = state.get("classification")
    await announce_progress(
        state,
        deps,
        "diagnosing",
        severity=classification.severity if classification else None,
    )

    async with node_context(deps) as ctx:
        unresolved: list[str] = []
        try:
            diagnosis, unresolved = await _run_diagnosis(state, deps, ctx, incident_id, bundle)
        except AIRefusalError:
            await ctx.audit.record(
                incident_id,
                EventType.AI_REFUSED.value,
                actor_type=ActorType.AI,
                actor_label="diagnose",
                summary="Model refused the diagnosis request",
            )
            diagnosis = _fallback_diagnosis(bundle, "Diagnosis refused by the model")
        except AIInvalidOutputError as exc:
            # Truncation / schema failure — NOT a refusal; the raw text and
            # validation detail are on the ai_analyses row.
            await ctx.audit.record(
                incident_id,
                EventType.AI_INVALID_OUTPUT.value,
                actor_type=ActorType.AI,
                actor_label="diagnose",
                summary=(
                    "Model output was truncated at the token ceiling"
                    if exc.truncated
                    else "Model output failed schema validation"
                ),
                payload={"detail": (exc.detail or "")[:2000], "truncated": exc.truncated},
            )
            diagnosis = _fallback_diagnosis(bundle, "Diagnosis output was unusable (not a refusal)")

        if unresolved:
            await ctx.audit.record(
                incident_id,
                EventType.AI_DIAGNOSED.value,
                actor_type=ActorType.AI,
                actor_label="diagnose",
                summary=(
                    f"Dropped {len(unresolved)} culprit reference(s) that did not "
                    f"resolve in the workspace clone"
                ),
                payload={"unresolved_culprits": unresolved},
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
