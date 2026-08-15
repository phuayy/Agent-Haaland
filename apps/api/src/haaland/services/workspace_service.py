"""Clones the target repo into a disposable per-incident directory. Nothing
downstream (code search, patch application, static checks, test execution)
ever touches the real repository directly — only this local clone, which is
deleted when the incident's workspace closes."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import git


@dataclass
class Workspace:
    incident_id: uuid.UUID
    path: Path
    base_sha: str
    repo: git.Repo

    def _contained(self, relative_path: str) -> Path | None:
        """Resolve and verify the target stays inside the workspace.
        `Path.is_relative_to`, not a string-prefix check — a prefix check
        wrongly admits sibling dirs like `/workspaces-evil` for a workspace
        at `/workspaces`."""
        target = (self.path / relative_path).resolve()
        return target if target.is_relative_to(self.path.resolve()) else None

    def read_file(self, relative_path: str) -> str | None:
        target = self._contained(relative_path)
        if target is None or not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, relative_path: str, content: str) -> None:
        target = self._contained(relative_path)
        if target is None:
            raise ValueError(f"path escapes workspace: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def iter_python_files(self):
        yield from self.path.rglob("*.py")

    def close(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


class WorkspaceService:
    def __init__(
        self,
        *,
        clone_token_provider: Callable[[], Awaitable[str | None]],
        workdir_root: Path | None = None,
    ) -> None:
        # Async provider, not a static token: GitHub App installation tokens
        # expire hourly, so the token is fetched per clone, not per process.
        self._clone_token_provider = clone_token_provider
        self._workdir_root = workdir_root or Path(tempfile.gettempdir()) / "haaland-workspaces"
        self._workdir_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _authed_url(repo_url: str, token: str | None) -> str:
        if token and repo_url.startswith("https://") and "@" not in repo_url:
            return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)
        return repo_url

    async def prepare(self, incident_id: uuid.UUID, repo_url: str, base_ref: str) -> Workspace:
        dest = self._workdir_root / str(incident_id)
        if dest.exists():
            shutil.rmtree(dest)

        token = await self._clone_token_provider()
        repo = await asyncio.to_thread(
            git.Repo.clone_from, self._authed_url(repo_url, token), dest, branch=base_ref, depth=50
        )
        base_sha = repo.head.commit.hexsha
        return Workspace(incident_id=incident_id, path=dest, base_sha=base_sha, repo=repo)

    def reopen(self, incident_id: uuid.UUID, path: str, base_sha: str) -> Workspace:
        """Reconstruct the accessor for an already-cloned workspace. Graph
        state only carries `workspace_path` (a str) between nodes — LangGraph
        checkpoints must be serialisable, and a git.Repo handle is not — so
        every node after prepare_workspace calls this instead of prepare()."""
        return Workspace(incident_id=incident_id, path=Path(path), base_sha=base_sha, repo=git.Repo(path))
