"""Clones the target repo into a disposable per-incident directory. Nothing
downstream (code search, patch application, static checks, test execution)
ever touches the real repository directly — only this local clone, which is
deleted when the incident's workspace closes."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Iterator
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

    def resolve(self, relative_path: str) -> Path | None:
        """Public containment check for read-only tooling (the code toolbox);
        same rule as read_file, without reading."""
        return self._contained(relative_path)

    def iter_python_files(self) -> Iterator[Path]:
        yield from self.path.rglob("*.py")

    def iter_files(self) -> Iterator[Path]:
        """Every regular file in the clone except VCS internals. Callers
        (the code toolbox) apply their own size/binary/vendor-dir filters."""
        for path in self.path.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                yield path

    def recent_commits(self, *, hours: int = 24, limit: int = 20) -> list[dict]:
        """Deployment context off the clone itself: the commits landed on
        base_ref in the last `hours`, newest first, with the files each one
        touched. For an alert-shaped incident with no traceback this is often
        the strongest localization signal available. Best-effort: a shallow
        clone or an unrelated git failure yields [], never an exception."""
        if self.repo is None:
            return []
        try:
            commits = list(self.repo.iter_commits(max_count=limit, since=f"{hours}.hours.ago"))
        except Exception:  # noqa: BLE001 — deploy context is optional evidence
            return []
        out: list[dict] = []
        for c in commits:
            try:
                files = list(c.stats.files)[:20]
            except Exception:  # noqa: BLE001 — stats need the parent commit; shallow edge
                files = []
            out.append(
                {
                    "sha": c.hexsha[:12],
                    "author": c.author.name if c.author else "?",
                    "date": c.committed_datetime.isoformat(),
                    "message": c.summary,
                    "files": files,
                }
            )
        return out

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

    async def ensure(
        self, incident_id: uuid.UUID, *, repo_url: str, base_ref: str, path: str, base_sha: str
    ) -> Workspace:
        """Reopen the clone at `path`, or rebuild it at `base_sha` when the
        directory is gone. Clones live on ephemeral disk (a container tmpdir):
        a graph resumed after a restart or redeploy — the reject-then-redraft
        path in particular — must not die on a workspace the platform wiped.
        The rebuild pins the original base commit, never the branch head,
        so a resumed run reasons about the same code the checkpoint did."""
        candidate = Path(path)
        if (candidate / ".git").exists():
            return self.reopen(incident_id, path, base_sha)

        workspace = await self.prepare(incident_id, repo_url, base_ref)
        if workspace.base_sha != base_sha:
            try:
                await asyncio.to_thread(workspace.repo.git.checkout, base_sha)
            except git.GitCommandError:
                # base_sha fell outside the shallow clone window — fetch the
                # exact commit (GitHub serves reachable SHA1s) and retry.
                await asyncio.to_thread(workspace.repo.git.fetch, "origin", base_sha)
                await asyncio.to_thread(workspace.repo.git.checkout, base_sha)
            workspace.base_sha = base_sha
        return workspace

    def cleanup(self, incident_id: uuid.UUID, path: str | None = None) -> None:
        """Delete the incident's disposable clone(s). Terminal nodes and the
        crash handler call this — nothing else deletes workspaces, and only
        paths inside the managed root are ever removed."""
        shutil.rmtree(self._workdir_root / str(incident_id), ignore_errors=True)
        if path:
            candidate = Path(path)
            if candidate.resolve().is_relative_to(self._workdir_root.resolve()):
                shutil.rmtree(candidate, ignore_errors=True)
