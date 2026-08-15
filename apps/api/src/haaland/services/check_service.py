"""Orchestrates static + dynamic checks against the patched workspace via a
SandboxRunner — never a raw subprocess call from here, so the allowlist and
network/timeout policy stay in one place (integrations/sandbox/*).

ast.parse and ruff never need the target repo's own dependencies, so they
always run. pytest does; if dependency install fails, that is recorded as
`unrunnable`, not `pass` — a check we silently skipped must never look the
same as a check that succeeded (see the plan's stated risk)."""

from __future__ import annotations

import json

from haaland.domain.enums import CheckOutcome
from haaland.domain.models import CheckFinding, CheckReport
from haaland.integrations.base import SandboxRunner
from haaland.services.workspace_service import Workspace


class CheckService:
    def __init__(self, runner: SandboxRunner, *, allow_unisolated_tests: bool = False) -> None:
        self._runner = runner
        self._allow_unisolated_tests = allow_unisolated_tests

    async def _check_syntax(self, workspace: Workspace, changed_paths: list[str]) -> CheckFinding:
        result = await self._runner.run(
            ["python", "-m", "py_compile", *changed_paths], cwd=str(workspace.path), timeout_seconds=30
        )
        if result.returncode == 0:
            return CheckFinding(tool="ast", outcome=CheckOutcome.PASS, summary="syntax OK")
        return CheckFinding(
            tool="ast", outcome=CheckOutcome.FAIL, summary="syntax error", detail=result.stderr
        )

    async def _check_ruff(self, workspace: Workspace, changed_paths: list[str]) -> CheckFinding:
        result = await self._runner.run(
            ["ruff", "check", "--output-format=json", *changed_paths],
            cwd=str(workspace.path),
            timeout_seconds=60,
        )
        if result.returncode == 0:
            return CheckFinding(tool="ruff", outcome=CheckOutcome.PASS, summary="ruff clean")
        try:
            violations = json.loads(result.stdout or "[]")
            summary = f"{len(violations)} ruff violation(s)"
        except json.JSONDecodeError:
            summary = "ruff reported violations"
        return CheckFinding(
            tool="ruff", outcome=CheckOutcome.FAIL, summary=summary, detail=result.stdout or result.stderr
        )

    async def run_static_checks(
        self, workspace: Workspace, changed_paths: list[str], attempt: int
    ) -> CheckReport:
        py_paths = [p for p in changed_paths if p.endswith(".py")]
        findings = []
        if py_paths:
            findings.append(await self._check_syntax(workspace, py_paths))
            findings.append(await self._check_ruff(workspace, py_paths))
        else:
            findings.append(
                CheckFinding(tool="ast", outcome=CheckOutcome.PASS, summary="no Python files changed")
            )

        any_failed = any(f.outcome == CheckOutcome.FAIL for f in findings)
        outcome = CheckOutcome.FAIL if any_failed else CheckOutcome.PASS
        return CheckReport(attempt=attempt, outcome=outcome, findings=findings)

    async def run_tests(
        self, workspace: Workspace, *, test_path: str | None, attempt: int, install_cmd: list[str] | None
    ) -> CheckReport:
        if not getattr(self._runner, "isolated", False) and not self._allow_unisolated_tests:
            # pytest executes the target repo's — and the model's — code.
            # On a non-containerised runner that means executing it on the
            # host, which requires an explicit opt-in
            # (HAALAND_ALLOW_HOST_TEST_EXECUTION=true). Static checks are
            # unaffected: py_compile and ruff parse, they never execute.
            return CheckReport(
                attempt=attempt,
                outcome=CheckOutcome.UNRUNNABLE,
                findings=[
                    CheckFinding(
                        tool="pytest",
                        outcome=CheckOutcome.UNRUNNABLE,
                        summary="tests not executed: sandbox is not isolated and host "
                        "execution is disabled (set HAALAND_ALLOW_HOST_TEST_EXECUTION=true "
                        "or run under Docker Compose)",
                    )
                ],
            )

        if install_cmd:
            install_result = await self._runner.run(
                install_cmd, cwd=str(workspace.path), timeout_seconds=180, network=True
            )
            if install_result.returncode != 0:
                return CheckReport(
                    attempt=attempt,
                    outcome=CheckOutcome.UNRUNNABLE,
                    findings=[
                        CheckFinding(
                            tool="pytest",
                            outcome=CheckOutcome.UNRUNNABLE,
                            summary="dependency install failed — tests not executed",
                            detail=install_result.stderr,
                        )
                    ],
                )

        argv = ["pytest", "-q"] + ([test_path] if test_path else [])
        result = await self._runner.run(argv, cwd=str(workspace.path), timeout_seconds=120, network=False)
        if result.timed_out:
            outcome = CheckOutcome.UNRUNNABLE
            summary = "pytest timed out"
        elif result.returncode == 0:
            outcome = CheckOutcome.PASS
            summary = "tests passed"
        else:
            outcome = CheckOutcome.FAIL
            summary = "tests failed"

        return CheckReport(
            attempt=attempt,
            outcome=outcome,
            findings=[
                CheckFinding(
                    tool="pytest", outcome=outcome, summary=summary, detail=result.stdout + result.stderr
                )
            ],
        )
