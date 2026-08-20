"""Stage 3 continued (docs/04's PR flow, steps 1-3): branch name is fixed at
`haaland/{incident_reference}-{strategy}` so an operator can find, and
delete, everything the agent ever created with one glob. Pushes only after
static checks (and, when runnable, tests) are green — a failed loop never
reaches this node."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context, workspace_from_state
from haaland.domain.enums import ActorType
from haaland.domain.events import EventType
from haaland.integrations.scm.github import parse_repo_url


async def push_branch_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = await workspace_from_state(deps, state)
    remediation = state["remediation"]
    diagnosis = state["diagnosis"]
    ref = parse_repo_url(state["repo_url"])
    branch_name = f"haaland/{state['reference']}-{remediation.strategy}"

    await deps.scm.create_branch(ref, branch_name, state["base_sha"])
    files = {p: workspace.read_file(p) for p in state["changed_paths"]}
    files = {p: c for p, c in files.items() if c is not None}
    await deps.scm.commit_files(ref, branch_name, files, message=remediation.pr_title)

    async with node_context(deps) as ctx:
        remediation_row = await ctx.remediations.create(
            incident_id=incident_id,
            strategy=remediation.strategy,
            rationale=diagnosis.strategy_rationale,
            risk_notes=remediation.risk_assessment,
            repo_full_name=state["repo_full_name"],
            branch_name=branch_name,
            base_sha=state["base_sha"],
            patch=state.get("combined_patch") or "",
            attempt_count=state.get("fix_attempt", 1),
        )
        await ctx.audit.record(
            incident_id,
            EventType.BRANCH_PUSHED.value,
            actor_type=ActorType.SYSTEM,
            actor_label="push_branch",
            summary=f"Pushed {branch_name} with {len(files)} file(s)",
            payload={"branch_name": branch_name, "files": list(files.keys())},
        )

    return {"branch_name": branch_name, "remediation_id": str(remediation_row.id)}
