"""Stage 4, first half. Runs once static checks are green — writes the test
file into the workspace; run_tests_node (next) proves it fails pre-fix and
passes post-fix before it's allowed to ship.

Deviation from docs/05: the docs ship the regression test as a *separate*
PR so a failing generated test never blocks the rollback PR. This slice
ships it in the same PR as the fix, appended to `changed_paths`, to keep the
loop's surface area tractable — noted here rather than silently narrowed."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType
from haaland.domain.events import EventType
from haaland.domain.models import RegressionTest
from haaland.llm.rendering import render_test_input


async def generate_tests_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = deps.workspace.reopen(incident_id, state["workspace_path"], state["base_sha"])
    remediation = state["remediation"]

    async with node_context(deps) as ctx:
        test = await ctx.llm_call.call(
            incident_id=incident_id,
            stage="test",
            redacted_text=render_test_input(
                state["diagnosis"],
                remediation.pr_title,
                state.get("changed_paths") or [],
                combined_patch=state.get("combined_patch"),
            ),
            output_schema=RegressionTest,
        )

        workspace.write_file(test.file_path, test.test_code)

        await ctx.audit.record(
            incident_id,
            EventType.TEST_GENERATED.value,
            actor_type=ActorType.AI,
            actor_label=deps.llm.name,
            summary=f"Generated regression test: {test.test_name} ({test.file_path})",
            payload={"file_path": test.file_path},
        )

    return {"regression_test": test}
