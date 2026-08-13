"""Compose-mode SandboxRunner: each check runs in a disposable
`docker run --rm` container, resource-capped and with `--network=none` for
the test phase (dependency install is the one step that needs `network`).
Requires the Docker socket mounted into the api/worker container — that
mount is compose-only, documented in docker-compose.yml, and deliberately
not part of the dev-default SubprocessRunner path."""

from __future__ import annotations

import asyncio

from haaland.integrations.base import CommandResult

_ALLOWED_EXECUTABLES = {"python", "ruff", "pytest", "git", "pip"}


class DockerRunner:
    def __init__(self, image: str = "python:3.12-slim", *, cpu_limit: str = "1", memory_limit: str = "512m"):
        self._image = image
        self._cpu_limit = cpu_limit
        self._memory_limit = memory_limit

    async def run(
        self, argv: list[str], *, cwd: str, timeout_seconds: int = 120, network: bool = False
    ) -> CommandResult:
        if not argv or argv[0] not in _ALLOWED_EXECUTABLES:
            raise ValueError(f"command not on the sandbox allowlist: {argv[:1]}")

        docker_argv = [
            "docker", "run", "--rm",
            "--network", "bridge" if network else "none",
            "--cpus", self._cpu_limit,
            "--memory", self._memory_limit,
            "-v", f"{cwd}:/workspace",
            "-w", "/workspace",
            self._image,
            *argv,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
