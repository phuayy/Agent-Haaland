"""Stage 4, second half — the gate from docs/05: run the generated test
against the pre-fix commit (must fail) and the post-fix commit (must pass).
A test passing on broken code is discarded silently rather than shipped.

The pre/post swap is done with `git stash` on just the fix's *source*
files — the newly generated test file is untracked, so stashing the fix
leaves the test in place and reverts only the code under test."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, CheckOutcome
from haaland.domain.events import EventType
from haaland.domain.models import TestValidation


def _infer_install_cmd(workspace) -> list[str] | None:
    if (workspace.path / "requirements.txt").is_file():
        return ["pip", "install", "-q", "-r", "requirements.txt"]
    if (workspace.path / "pyproject.toml").is_file():
        return ["pip", "install", "-q", "-e", "."]
    return None


async def run_tests_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = deps.workspace.reopen(incident_id, state["workspace_path"], state["base_sha"])
    test = state["regression_test"]
    source_paths = [p for p in (state.get("changed_paths") or []) if p != test.file_path]
    install_cmd = _infer_install_cmd(workspace)

    post_fix_report = await deps.check.run_tests(
        workspace, test_path=test.file_path, attempt=1, install_cmd=install_cmd
    )

    if post_fix_report.outcome == CheckOutcome.UNRUNNABLE:
        outcome = "unrunnable"
        validation = TestValidation(
            fails_on_base=False, passes_on_fix=False, accepted=False,
            detail="Environment could not run the target repo's test suite — "
            "PR opened flagged 'tests not executed', not claimed green.",
        )
    else:
        passes_on_fix = post_fix_report.outcome == CheckOutcome.PASS
        fails_on_base = False
        if source_paths:
            workspace.repo.git.stash("push", "--", *source_paths)
            try:
                pre_fix_report = await deps.check.run_tests(
                    workspace, test_path=test.file_path, attempt=1, install_cmd=None
                )
                fails_on_base = pre_fix_report.outcome == CheckOutcome.FAIL
            finally:
                workspace.repo.git.stash("pop")

        accepted = passes_on_fix and fails_on_base
        outcome = "accepted" if accepted else "failed"
        validation = TestValidation(
            fails_on_base=fails_on_base,
            passes_on_fix=passes_on_fix,
            accepted=accepted,
            detail="fails pre-fix and passes post-fix" if accepted
            else "discarded: did not reproduce-then-resolve as required",
        )

    async with node_context(deps) as ctx:
        await ctx.audit.record(
            incident_id,
            EventType.TEST_VALIDATED.value,
            actor_type=ActorType.SYSTEM,
            actor_label="run_tests",
            summary=f"Regression test validation: {validation.detail}",
            payload=validation.model_dump(mode="json"),
        )

    changed_paths = list(state.get("changed_paths") or [])
    if validation.accepted and test.file_path not in changed_paths:
        changed_paths.append(test.file_path)

    return {
        "test_validation_accepted": validation.accepted,
        "test_outcome": outcome,
        "changed_paths": changed_paths,
        "last_failure_detail": None if validation.accepted else validation.detail,
    }
