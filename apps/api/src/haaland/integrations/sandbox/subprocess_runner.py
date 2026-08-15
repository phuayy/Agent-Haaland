"""Dev-mode SandboxRunner: runs the fixed allowlisted commands as a host
subprocess inside the host's own `uv` venv. No model-supplied argv ever
reaches this — callers (check_service.py) build the argv list themselves
from a closed set of tool names."""

from __future__ import annotations

import asyncio

from haaland.integrations.base import CommandResult

_ALLOWED_EXECUTABLES = {"python", "ruff", "pytest", "git", "pip"}


class SubprocessRunner:
    isolated = False  # host process — CheckService gates the pytest phase on this

    async def run(
        self, argv: list[str], *, cwd: str, timeout_seconds: int = 120, network: bool = False
    ) -> CommandResult:
        if not argv or argv[0] not in _ALLOWED_EXECUTABLES:
            raise ValueError(f"command not on the sandbox allowlist: {argv[:1]}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            return CommandResult(
                command=argv,
                returncode=proc.returncode or 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
            )
        except TimeoutError:
            return CommandResult(command=argv, returncode=-1, stdout="", stderr="timed out", timed_out=True)
