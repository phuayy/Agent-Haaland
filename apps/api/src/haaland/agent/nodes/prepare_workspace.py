"""Clones the target repo at base_ref into a disposable directory. Every
node from here on that needs the source (locate_code, apply_patch,
static_check, run_tests) reads/writes only inside this clone — never the
real repository — until push_branch commits the verified result upstream."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType
from haaland.domain.events import EventType


async def prepare_workspace_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = await deps.workspace.prepare(incident_id, state["repo_url"], state["base_ref"])

    async with node_context(deps) as ctx:
        await ctx.audit.record(
            incident_id,
            EventType.WORKSPACE_PREPARED.value,
            actor_type=ActorType.SYSTEM,
            actor_label="prepare_workspace",
            summary=f"Cloned {state['repo_full_name']}@{state['base_ref']} ({workspace.base_sha[:8]})",
            payload={"base_sha": workspace.base_sha},
        )

    return {"workspace_path": str(workspace.path), "base_sha": workspace.base_sha}
