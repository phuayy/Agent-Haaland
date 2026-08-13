"""Post-parse policy enforcement (docs/09 layer 1) — the model's output is
constrained by schema (no delete/execute action, max 10 files), and this
module enforces the parts a schema cannot: path traversal and the protected-
path denylist. A rejection here is a security signal, not a retry
condition — it is recorded as `ai.remediation_rejected_by_policy` and never
silently swallowed."""

from __future__ import annotations

import difflib
import re
from pathlib import PurePosixPath

from haaland.domain.errors import RemediationRejected
from haaland.domain.models import FileChange
from haaland.services.workspace_service import Workspace

DENYLIST = [
    ".github/workflows/**", ".github/actions/**",
    "**/*secret*", "**/*credential*", "**/.env*",
    "**/Dockerfile", "infra/**", "terraform/**", "**/*.tf",
    "**/authorized_keys", "**/id_rsa*",
]

MAX_FILES = 10


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`PurePosixPath.match()` treats `**` as a single-component wildcard,
    not "zero or more directories" — under Python 3.12 it silently fails to
    catch `infra/nested/x.yml` against `infra/**`, or a root-level
    `secret.txt` against `**/*secret*` (no leading directory for `**` to
    consume). That is a real gap in a security denylist, so patterns are
    matched with a hand-translated regex instead of `PurePath.match`."""
    out = []
    i = 0
    while i < len(pattern):
        if pattern[i : i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


_DENYLIST_PATTERNS = [_glob_to_regex(pat) for pat in DENYLIST]


def validate_file_change(fc: FileChange, workspace: Workspace) -> None:
    p = PurePosixPath(fc.path)
    if p.is_absolute() or ".." in p.parts:
        raise RemediationRejected(f"path traversal: {fc.path}")
    if any(pat.match(fc.path) for pat in _DENYLIST_PATTERNS):
        raise RemediationRejected(f"protected path: {fc.path}")
    if fc.action.value == "revert" and workspace.read_file(fc.path) is None:
        raise RemediationRejected(f"cannot revert non-existent file: {fc.path}")


def apply_changes(files: list[FileChange], workspace: Workspace) -> dict[str, str]:
    """Validates, writes each file into the workspace, and returns a unified
    diff per path — computed by us against the real on-disk content, never
    taken from the model (docs/05: eliminates a whole class of malformed-
    diff failures)."""
    if len(files) > MAX_FILES:
        raise RemediationRejected(f"{len(files)} files exceeds the {MAX_FILES}-file ceiling")

    diffs: dict[str, str] = {}
    for fc in files:
        validate_file_change(fc, workspace)
        before = workspace.read_file(fc.path) or ""
        workspace.write_file(fc.path, fc.new_content)
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                fc.new_content.splitlines(keepends=True),
                fromfile=f"a/{fc.path}",
                tofile=f"b/{fc.path}",
            )
        )
        diffs[fc.path] = diff
    return diffs


def combined_patch(diffs: dict[str, str]) -> str:
    return "\n".join(diffs.values())
