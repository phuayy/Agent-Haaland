"""Stage 3, first half: turn the selected fix into concrete file changes and
write them into the local workspace clone. `patch_service.apply_changes`
enforces the path denylist and file-count ceiling *after* parsing — the
schema can't express delete/execute, but it can't stop a path traversal or
a `.github/workflows` edit either, so that check happens here in code
(docs/09 layer 1)."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType
from haaland.domain.errors import RemediationRejected
from haaland.domain.events import EventType
from haaland.domain.models import RemediationDraft
from haaland.llm.rendering import render_remediate_input
from haaland.services.patch_service import apply_changes, combined_patch


async def apply_patch_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = deps.workspace.reopen(incident_id, state["workspace_path"], state["base_sha"])

    async with node_context(deps) as ctx:
        remediation = await ctx.llm_call.call(
            incident_id=incident_id,
            stage="remediate",
            redacted_text=render_remediate_input(state["diagnosis"], state["fix_evaluation"]),
            output_schema=RemediationDraft,
        )

        try:
            diffs = apply_changes(remediation.files, workspace)
        except RemediationRejected as exc:
            await ctx.audit.record(
                incident_id,
                EventType.REMEDIATION_REJECTED_BY_POLICY.value,
                actor_type=ActorType.SYSTEM,
                actor_label="apply_patch",
                summary=f"Remediation rejected by policy: {exc}",
                payload={"reason": str(exc)},
            )
            return {
                "remediation": remediation,
                "changed_paths": [],
                "combined_patch": None,
                "last_failure_detail": f"Policy rejection: {exc}",
            }

        await ctx.audit.record(
            incident_id,
            EventType.PATCH_APPLIED.value,
            actor_type=ActorType.AI,
            actor_label=deps.llm.name,
            summary=f"Applied patch across {len(diffs)} file(s): {remediation.pr_title}",
            payload={"changed_paths": list(diffs.keys())},
        )

    return {
        "remediation": remediation,
        "changed_paths": list(diffs.keys()),
        "combined_patch": combined_patch(diffs),
    }
