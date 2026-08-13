"""Parses .github/CODEOWNERS (GitHub's own format: `pattern owner1 owner2`,
last matching pattern wins) and maps the PR's changed paths to reviewers to
request. Falls back to no requested reviewers rather than failing the PR —
a missing CODEOWNERS file is common and must not block opening the PR."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass


@dataclass(frozen=True)
class _Rule:
    pattern: str
    owners: tuple[str, ...]


def _parse(codeowners_text: str) -> list[_Rule]:
    rules = []
    for line in codeowners_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        pattern, owners = parts[0], tuple(o.lstrip("@") for o in parts[1:])
        rules.append(_Rule(pattern=pattern, owners=owners))
    return rules


def _matches(pattern: str, path: str) -> bool:
    pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        return path.startswith(pattern)
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, f"{pattern.rstrip('*')}*")


class CodeownersService:
    def reviewers_for(self, codeowners_text: str | None, changed_paths: list[str]) -> list[str]:
        if not codeowners_text:
            return []
        rules = _parse(codeowners_text)
        reviewers: set[str] = set()
        for path in changed_paths:
            owners_for_path: tuple[str, ...] = ()
            for rule in rules:  # last match wins, per GitHub's own semantics
                if _matches(rule.pattern, path):
                    owners_for_path = rule.owners
            reviewers.update(o for o in owners_for_path if "/" not in o)  # skip team @org/team for now
        return sorted(reviewers)
