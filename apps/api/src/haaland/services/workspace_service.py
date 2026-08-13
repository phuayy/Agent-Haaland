"""Clones the target repo into a disposable per-incident directory. Nothing
downstream (code search, patch application, static checks, test execution)
ever touches the real repository directly — only this local clone, which is
deleted when the incident's workspace closes."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import git


@dataclass
class Workspace:
    incident_id: uuid.UUID
    path: Path
    base_sha: str
    repo: git.Repo

    def read_file(self, relative_path: str) -> str | None:
        target = (self.path / relative_path).resolve()
        if not str(target).startswith(str(self.path.resolve())):
            return None  # traversal guard, mirrors patch_service's denylist check
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, relative_path: str, content: str) -> None:
        target = (self.path / relative_path).resolve()
        if not str(target).startswith(str(self.path.resolve())):
            raise ValueError(f"path escapes workspace: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def iter_python_files(self):
        yield from self.path.rglob("*.py")

    def close(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


class WorkspaceService:
    def __init__(self, *, github_token: str | None, workdir_root: Path | None = None) -> None:
        self._token = github_token
        self._workdir_root = workdir_root or Path(tempfile.gettempdir()) / "haaland-workspaces"
        self._workdir_root.mkdir(parents=True, exist_ok=True)

    def _authed_url(self, repo_url: str) -> str:
        if self._token and repo_url.startswith("https://") and "@" not in repo_url:
            return repo_url.replace("https://", f"https://{self._token}@", 1)
        return repo_url

    async def prepare(self, incident_id: uuid.UUID, repo_url: str, base_ref: str) -> Workspace:
        dest = self._workdir_root / str(incident_id)
        if dest.exists():
            shutil.rmtree(dest)

        repo = await asyncio.to_thread(
            git.Repo.clone_from, self._authed_url(repo_url), dest, branch=base_ref, depth=50
        )
        base_sha = repo.head.commit.hexsha
        return Workspace(incident_id=incident_id, path=dest, base_sha=base_sha, repo=repo)

    def reopen(self, incident_id: uuid.UUID, path: str, base_sha: str) -> Workspace:
        """Reconstruct the accessor for an already-cloned workspace. Graph
        state only carries `workspace_path` (a str) between nodes — LangGraph
        checkpoints must be serialisable, and a git.Repo handle is not — so
        every node after prepare_workspace calls this instead of prepare()."""
        return Workspace(incident_id=incident_id, path=Path(path), base_sha=base_sha, repo=git.Repo(path))
