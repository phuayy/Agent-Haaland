from __future__ import annotations

from haaland.agent.nodes._context import node_context, workspace_from_state
from haaland.domain.enums import ActorType
from haaland.domain.events import EventType


async def static_check_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = await workspace_from_state(deps, state)
    changed_paths = state.get("changed_paths") or []
    attempt = state.get("fix_attempt", 1)

    if not changed_paths:
        # apply_patch already rejected the draft by policy — nothing to check.
        report = None
        outcome = "fail"
        detail = state.get("last_failure_detail", "no files were applied")
    else:
        report = await deps.check.run_static_checks(workspace, changed_paths, attempt)
        outcome = report.outcome.value
        failing = [f for f in report.findings if f.outcome.value != "pass"]
        detail = "\n".join(f"[{f.tool}] {f.summary}\n{f.detail}" for f in failing)

    async with node_context(deps) as ctx:
        await ctx.audit.record(
            incident_id,
            EventType.CHECK_RAN.value,
            actor_type=ActorType.SYSTEM,
            actor_label="static_check",
            summary=f"Static checks attempt {attempt}: {outcome}",
            payload={"attempt": attempt, "outcome": outcome},
        )

    reports = list(state.get("check_reports") or [])
    if report is not None:
        reports.append(report.model_dump(mode="json"))
    else:
        # A policy-rejected draft must still land a failing entry: the router
        # reads `check_reports[-1]`, and on any attempt after a previously
        # green one the stale "pass" would otherwise send an empty patch
        # forward to generate_tests.
        reports.append({"attempt": attempt, "outcome": outcome, "findings": []})

    return {
        "check_reports": reports,
        "last_failure_detail": detail if outcome != "pass" else None,
    }
