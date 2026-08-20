"""Read-only, workspace-scoped tools for the agentic exploration loop —
the Claude Code read/grep vocabulary (grep, read_file, glob, list_dir) plus
find_symbol, which leans on the same one-pass AST index that
code_search_service already builds for candidate ranking.

Three invariants, enforced here rather than trusted to the model:

1. containment — every path resolves through Workspace.resolve, so nothing
   outside the per-incident clone is readable, no matter what the model asks
   for;
2. bounded output — every tool caps matches, lines and total characters, so
   a hub file or a greedy regex cannot flood the context window (and the
   budget) in one call;
3. read-only — the loop explores; only apply_patch mutates, and it never
   goes through this module.

Tool inputs are Pydantic models: their JSON Schema is what the provider
advertises to the model, and validation of the model's arguments happens
here against the very same schema. A malformed call becomes an is_error
tool result the model can correct — never an exception up the loop.
"""

from __future__ import annotations

import ast
import fnmatch
import re
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from haaland.llm.tools import ToolCall, ToolSpec
from haaland.services.workspace_service import Workspace

_SKIP_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox",
     ".mypy_cache", ".ruff_cache", "dist", "build"}
)
_MAX_FILE_BYTES = 1_000_000
_MAX_OUTPUT_CHARS = 20_000
_MAX_GREP_MATCHES = 50
_MAX_GLOB_RESULTS = 200
_MAX_READ_LINES = 400
_BINARY_SNIFF_BYTES = 8192

_TRUNCATED = "\n[output truncated]"


class GrepParams(BaseModel):
    pattern: str = Field(description="Python regular expression, matched against each line of each file.")
    glob: str | None = Field(
        default=None,
        description="Only search files whose repo-relative path matches this glob, e.g. '*.py' or 'src/*'.",
    )
    context_lines: int = Field(
        default=0, ge=0, le=5, description="Lines of context to show before and after each match."
    )
    max_matches: int = Field(default=_MAX_GREP_MATCHES, ge=1, le=_MAX_GREP_MATCHES)


class ReadFileParams(BaseModel):
    path: str = Field(description="Repo-relative file path.")
    offset: int = Field(default=1, ge=1, description="1-based line number to start reading from.")
    limit: int = Field(default=200, ge=1, le=_MAX_READ_LINES, description="Maximum number of lines to read.")


class GlobParams(BaseModel):
    pattern: str = Field(description="Path glob matched against repo-relative paths, e.g. 'src/*/models.py'.")


class ListDirParams(BaseModel):
    path: str = Field(default=".", description="Repo-relative directory path; '.' for the repo root.")


class FindSymbolParams(BaseModel):
    name: str = Field(description="Exact function, method or class name to locate (Python files only).")


class CodeToolbox:
    """The tool surface one incident's exploration loop sees. Stateless per
    call; holds only the workspace handle."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    # -- tool registry -------------------------------------------------

    _TOOLS: dict[str, tuple[type[BaseModel], str]] = {
        "grep": (
            GrepParams,
            "Search file contents with a regular expression. Returns 'path:line: text' matches. "
            "Use to find callers, definitions, config keys, or error-message literals.",
        ),
        "read_file": (
            ReadFileParams,
            "Read a file with line numbers. Use offset/limit to page through large files.",
        ),
        "glob": (
            GlobParams,
            "List files whose repo-relative path matches a glob pattern.",
        ),
        "list_dir": (
            ListDirParams,
            "List one directory level: entries with a trailing '/' are directories.",
        ),
        "find_symbol": (
            FindSymbolParams,
            "Locate the definition(s) of a Python function, method or class by exact name, "
            "with file, line span and signature line.",
        ),
    }

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=name, description=description, input_schema=params.model_json_schema())
            for name, (params, description) in self._TOOLS.items()
        ]

    def execute(self, call: ToolCall) -> tuple[str, bool]:
        """Run one tool call. Returns (content, is_error) — errors are text
        the model can read and correct, never exceptions."""
        entry = self._TOOLS.get(call.name)
        if entry is None:
            return f"unknown tool: {call.name}", True
        params_model, _ = entry
        try:
            params = params_model.model_validate(call.arguments)
        except ValidationError as exc:
            return f"invalid arguments for {call.name}: {exc}", True
        try:
            handler = getattr(self, f"_{call.name}")
            return _clip(handler(params)), False
        except _ToolError as exc:
            return str(exc), True

    # -- filesystem helpers --------------------------------------------

    def _iter_searchable(self) -> Iterator[tuple[str, Path]]:
        """Repo files worth reading: vendor/VCS dirs, oversized files and
        binaries excluded. Yields (rel_path, absolute_path)."""
        for path in self._workspace.iter_files():
            rel = path.relative_to(self._workspace.path).as_posix()
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                with path.open("rb") as fh:
                    if b"\x00" in fh.read(_BINARY_SNIFF_BYTES):
                        continue
            except OSError:
                continue
            yield rel, path

    def _read_contained(self, rel_path: str) -> str:
        content = self._workspace.read_file(rel_path)
        if content is None:
            raise _ToolError(f"file not found (or outside the workspace): {rel_path}")
        return content

    # -- tools -----------------------------------------------------------

    def _grep(self, p: GrepParams) -> str:
        try:
            rx = re.compile(p.pattern)
        except re.error as exc:
            raise _ToolError(f"invalid regular expression: {exc}") from exc

        out: list[str] = []
        matched = 0
        for rel, _path in self._iter_searchable():
            if p.glob and not fnmatch.fnmatch(rel, p.glob):
                continue
            lines = self._read_contained(rel).splitlines()
            for i, line in enumerate(lines, start=1):
                if not rx.search(line):
                    continue
                matched += 1
                if p.context_lines:
                    lo, hi = max(1, i - p.context_lines), min(len(lines), i + p.context_lines)
                    out.extend(f"{rel}:{n}: {lines[n - 1]}" for n in range(lo, hi + 1))
                    out.append("--")
                else:
                    out.append(f"{rel}:{i}: {line}")
                if matched >= p.max_matches:
                    out.append(f"[stopped at {p.max_matches} matches — narrow the pattern or add a glob]")
                    return "\n".join(out)
        return "\n".join(out) if out else "no matches"

    def _read_file(self, p: ReadFileParams) -> str:
        lines = self._read_contained(p.path).splitlines()
        total = len(lines)
        if p.offset > total:
            raise _ToolError(f"{p.path} has only {total} line(s); offset {p.offset} is past the end")
        window = lines[p.offset - 1 : p.offset - 1 + p.limit]
        body = "\n".join(f"{n}: {line}" for n, line in enumerate(window, start=p.offset))
        shown_to = p.offset + len(window) - 1
        if shown_to < total:
            body += f"\n[showing lines {p.offset}-{shown_to} of {total}; continue with offset={shown_to + 1}]"
        return body

    def _glob(self, p: GlobParams) -> str:
        matches = sorted(rel for rel, _ in self._iter_searchable() if fnmatch.fnmatch(rel, p.pattern))
        if len(matches) > _MAX_GLOB_RESULTS:
            extra = len(matches) - _MAX_GLOB_RESULTS
            matches = matches[:_MAX_GLOB_RESULTS] + [f"[{extra} more not shown — narrow the pattern]"]
        return "\n".join(matches) if matches else "no files match"

    def _list_dir(self, p: ListDirParams) -> str:
        target = self._workspace.resolve(p.path)
        if target is None or not target.is_dir():
            raise _ToolError(f"directory not found (or outside the workspace): {p.path}")
        entries = sorted(
            (e.name + "/" if e.is_dir() else e.name)
            for e in target.iterdir()
            if e.name not in _SKIP_DIRS
        )
        return "\n".join(entries) if entries else "(empty)"

    def _find_symbol(self, p: FindSymbolParams) -> str:
        out: list[str] = []
        for rel, _path in self._iter_searchable():
            if not rel.endswith(".py"):
                continue
            content = self._read_contained(rel)
            try:
                tree = ast.parse(content, filename=rel)
            except SyntaxError:
                continue
            lines = content.splitlines()
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                    and node.name == p.name
                ):
                    end = getattr(node, "end_lineno", node.lineno)
                    signature = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                    out.append(f"{rel}:{node.lineno}-{end}: {signature}")
        return "\n".join(out) if out else f"no definition of {p.name!r} found"


class _ToolError(Exception):
    """A tool-level failure the model should see as an is_error result."""


def _clip(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[: _MAX_OUTPUT_CHARS - len(_TRUNCATED)] + _TRUNCATED
