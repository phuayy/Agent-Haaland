"""The orchestrator and every service import Protocols from here, never a
vendor SDK directly. Swapping GitHub for GitLab, or Prometheus for Datadog,
is a config change plus one adapter class (docs/01, docs/02)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from haaland.domain.models import LogLine, NotificationMessage, TimeWindow


class SignalSource(Protocol):
    def parse(self, raw: dict) -> list[dict]: ...
    def verify(self, headers: Mapping[str, str], body: bytes) -> bool: ...


class LogSource(Protocol):
    async def query(self, service: str, window: TimeWindow, filters: dict) -> list[LogLine]: ...


class TraceSource(Protocol):
    async def find_exemplar(self, service: str, window: TimeWindow, min_duration_ms: int): ...
    async def get_trace(self, trace_id: str): ...


@dataclass
class RepoRef:
    owner: str
    repo: str
    default_branch: str = "main"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass
class PullRequestResult:
    number: int
    url: str
    branch_name: str


class SCMProvider(Protocol):
    """Contents RW, Pull requests RW — and deliberately nothing more.
    There is no merge() method on this Protocol. See docs/09: the absence
    of a merge capability is the actual safety control, not a policy."""

    async def get_default_branch_sha(self, ref: RepoRef, branch: str) -> str: ...
    async def get_file_contents(self, ref: RepoRef, path: str, sha: str) -> str | None: ...
    async def create_branch(self, ref: RepoRef, branch_name: str, base_sha: str) -> None: ...
    async def commit_files(
        self, ref: RepoRef, branch_name: str, files: dict[str, str], message: str
    ) -> str: ...
    async def open_pull_request(
        self,
        ref: RepoRef,
        *,
        branch_name: str,
        base_branch: str,
        title: str,
        body: str,
        labels: list[str],
        reviewers: list[str],
    ) -> PullRequestResult: ...
    async def get_codeowners(self, ref: RepoRef, sha: str) -> str | None: ...
    async def clone_url(self, ref: RepoRef) -> str: ...


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxRunner(Protocol):
    """A fixed allowlist, no model-supplied argv, run against a disposable
    clone. This is the boundary that keeps the debug loop from becoming an
    arbitrary-code-execution tool (docs/09 layer 1).

    `isolated` states whether commands run inside a real container. Running
    pytest executes the target repo's (and the model's) code, so
    CheckService refuses the test phase on a non-isolated runner unless
    explicitly allowed by config."""

    isolated: bool

    async def run(
        self, argv: list[str], *, cwd: str, timeout_seconds: int = 120, network: bool = False
    ) -> CommandResult: ...


class Notifier(Protocol):
    """One instance per configured channel (integrations/notify/registry.py).
    `send` returns the channel's external reference (message id / request
    id) for the notifications audit row. Adapters raise NotificationError
    on failure; the NotificationService catches it — one channel being down
    must never fail the incident pipeline."""

    name: str

    async def send(self, message: NotificationMessage) -> str: ...


class NotificationError(Exception):
    """Raised by a Notifier when delivery fails."""


class TicketProvider(Protocol):
    async def create_ticket(self, *, title: str, description: str, evidence: dict) -> str: ...
