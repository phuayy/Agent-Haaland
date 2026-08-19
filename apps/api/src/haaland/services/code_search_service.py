"""Stage 1's deterministic half. Turns a stack trace and an error message
into ranked file:line candidates *before* the model reasons about them —
the model then explains and selects among candidates we already located,
rather than being asked to find a needle in an entire repository (docs/04's
"never paste an entire repository into a prompt" principle, applied to
source code instead of logs).

Locating runs in three passes, cheapest signal first:

1. traceback frames — file:line straight from the log, snippet widened to
   the enclosing function via AST;
2. grep fallbacks — the failing function's name (`def <name>`) when a
   frame's path doesn't map into the clone, and the error-signature text;
3. symbol references — one hop outward from the primaries along the call
   graph (callers and callees defined in this repo), so the diagnosis
   prompt carries the failing function's neighbourhood, not just the frame
   the exception surfaced in.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from haaland.domain.models import CodeLocation
from haaland.services.workspace_service import Workspace

_TRACEBACK_FRAME = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\S+))?')
_MAX_PRIMARY = 8
_MAX_RELATED = 4
_CONTEXT_LINES = 6


def parse_traceback_frames(log_text: str) -> list[tuple[str, int, str | None]]:
    return [(m.group(1), int(m.group(2)), m.group(3)) for m in _TRACEBACK_FRAME.finditer(log_text)]


def extract_call_chain(log_text: str) -> list[str]:
    """Function names outermost-first, straight off the traceback frames —
    the failure's workflow, rendered into the diagnosis prompt so the model
    sees the path the request took, not just where it died."""
    chain: list[str] = []
    for _path, _line, func in parse_traceback_frames(log_text):
        if func and func != "<module>" and (not chain or chain[-1] != func):
            chain.append(func)
    return chain


def _extract_error_signature(log_text: str) -> str | None:
    """The last 'SomeError: message' style line, if any — a decent proxy for
    the error signature grouping docs/04 describes for the Loki adapter."""
    lines = [line.strip() for line in log_text.strip().splitlines() if line.strip()]
    pattern = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b:?\s*(.*)")
    for line in reversed(lines):
        m = pattern.search(line)
        if m:
            message = m.group(2).strip()
            return message or m.group(1)
    return None


@dataclass(frozen=True)
class _FunctionInfo:
    path: str
    name: str
    start: int
    end: int
    calls: frozenset[str]


class _CalledNames(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 — ast visitor API
        func = node.func
        if isinstance(func, ast.Name):
            self.names.add(func.id)
        elif isinstance(func, ast.Attribute):
            self.names.add(func.attr)
        self.generic_visit(node)


def _index_functions(workspace: Workspace) -> list[_FunctionInfo]:
    """One AST pass over the clone: every function's span plus the names it
    calls. This is the whole 'call graph' — deliberately name-based, not
    resolved: for locating candidates, a false caller edge costs one extra
    snippet; a missed edge costs the model its only view of the culprit."""
    functions: list[_FunctionInfo] = []
    for path in workspace.iter_python_files():
        rel_path = path.relative_to(workspace.path).as_posix()
        content = workspace.read_file(rel_path)
        if content is None:
            continue
        try:
            tree = ast.parse(content, filename=rel_path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                collector = _CalledNames()
                collector.visit(node)
                functions.append(
                    _FunctionInfo(
                        path=rel_path,
                        name=node.name,
                        start=node.lineno,
                        end=getattr(node, "end_lineno", node.lineno),
                        calls=frozenset(collector.names),
                    )
                )
    return functions


def _enclosing_function_range(tree: ast.Module, line: int) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= line <= end and (best is None or (end - node.lineno) < (best[1] - best[0])):
                best = (node.lineno, end)
    return best


def _relative_path(workspace: Workspace, raw_path: str) -> str | None:
    """Traceback frames carry absolute paths from wherever the error
    originally ran; normalise to a path relative to the cloned workspace by
    matching the trailing path segments."""
    raw = raw_path.replace("\\", "/")
    for candidate in workspace.iter_python_files():
        rel = candidate.relative_to(workspace.path).as_posix()
        if raw.endswith(rel):
            return rel
    return None


def _snippet(workspace: Workspace, rel_path: str, start: int, end: int) -> str:
    content = workspace.read_file(rel_path) or ""
    lines = content.splitlines()
    lo = max(1, start) - 1
    hi = min(len(lines), end)
    return "\n".join(lines[lo:hi])


class CodeSearchService:
    def locate(self, workspace: Workspace, log_text: str) -> list[CodeLocation]:
        index = _index_functions(workspace)
        candidates: dict[tuple[str, int, int], CodeLocation] = {}
        unresolved_functions: list[str] = []

        frames = parse_traceback_frames(log_text)
        for depth, (raw_path, line, func) in enumerate(frames):
            rel_path = _relative_path(workspace, raw_path)
            if rel_path is None:
                if func and func != "<module>":
                    unresolved_functions.append(func)
                continue
            content = workspace.read_file(rel_path)
            if content is None:
                continue
            try:
                tree = ast.parse(content, filename=rel_path)
            except SyntaxError:
                start, end = max(1, line - _CONTEXT_LINES), line + _CONTEXT_LINES
            else:
                enclosing = _enclosing_function_range(tree, line)
                start, end = enclosing or (max(1, line - _CONTEXT_LINES), line + _CONTEXT_LINES)

            # A traceback lists frames outermost-first; the *last* frame is
            # where the exception actually raised and the far more likely
            # root cause, so it must outrank earlier call-site frames rather
            # than tying with them — otherwise ranking degenerates to
            # insertion order.
            confidence = min(0.95, 0.75 + 0.05 * (depth + 1))

            key = (rel_path, start, end)
            candidates[key] = CodeLocation(
                path=rel_path,
                start_line=start,
                end_line=end,
                snippet=_snippet(workspace, rel_path, start, end),
                reason="traceback_frame",
                confidence=confidence,
            )

        # Frames whose paths don't map into the clone (the log came from a
        # container layout, a different checkout, a vendored copy) still name
        # the failing function — grep the definition instead of dropping the
        # frame on the floor.
        for func_name in unresolved_functions:
            for info in index:
                if info.name != func_name:
                    continue
                key = (info.path, info.start, info.end)
                if key in candidates:
                    continue
                candidates[key] = CodeLocation(
                    path=info.path,
                    start_line=info.start,
                    end_line=info.end,
                    snippet=_snippet(workspace, info.path, info.start, info.end),
                    reason="function_name_grep",
                    confidence=0.6,
                )

        signature = _extract_error_signature(log_text)
        if signature:
            needle = signature[:80]
            for path in workspace.iter_python_files():
                rel_path = path.relative_to(workspace.path).as_posix()
                content = workspace.read_file(rel_path) or ""
                idx = content.find(needle)
                if idx == -1:
                    continue
                line_no = content.count("\n", 0, idx) + 1
                start, end = max(1, line_no - _CONTEXT_LINES), line_no + _CONTEXT_LINES
                key = (rel_path, start, end)
                if key in candidates:
                    continue
                candidates[key] = CodeLocation(
                    path=rel_path,
                    start_line=start,
                    end_line=end,
                    snippet=_snippet(workspace, rel_path, start, end),
                    reason="error_signature_grep",
                    confidence=0.5,
                )

        primaries = sorted(candidates.values(), key=lambda c: c.confidence, reverse=True)[:_MAX_PRIMARY]
        related = self._expand_symbol_references(workspace, index, primaries, candidates)
        return primaries + related

    def _expand_symbol_references(
        self,
        workspace: Workspace,
        index: list[_FunctionInfo],
        primaries: list[CodeLocation],
        seen: dict[tuple[str, int, int], CodeLocation],
    ) -> list[CodeLocation]:
        """One hop outward from each primary along the name-based call graph:
        the functions it calls (callees — the fix may belong a level deeper)
        and the functions that call it (callers — the bad argument usually
        originates upstream). Bounded to a single hop and _MAX_RELATED total
        so a hub function can't flood the prompt."""
        by_name: dict[str, list[_FunctionInfo]] = {}
        for f in index:
            by_name.setdefault(f.name, []).append(f)

        related: list[CodeLocation] = []
        for primary in primaries:
            enclosing = None
            for info in index:
                if (
                    info.path == primary.path
                    and info.start <= primary.start_line <= info.end
                    and (enclosing is None or (info.end - info.start) < (enclosing.end - enclosing.start))
                ):
                    enclosing = info
            if enclosing is None:
                continue

            neighbours: list[tuple[_FunctionInfo, str, float]] = []
            for called_name in sorted(enclosing.calls):
                for callee in by_name.get(called_name, []):
                    if callee is not enclosing:
                        neighbours.append((callee, f"callee of {enclosing.name}", 0.4))
            for caller in index:
                if caller is not enclosing and enclosing.name in caller.calls:
                    neighbours.append((caller, f"caller of {enclosing.name}", 0.45))

            for info, relation, confidence in neighbours:
                key = (info.path, info.start, info.end)
                if key in seen:
                    continue
                if len(related) >= _MAX_RELATED:
                    return related
                seen[key] = CodeLocation(
                    path=info.path,
                    start_line=info.start,
                    end_line=info.end,
                    snippet=_snippet(workspace, info.path, info.start, info.end),
                    reason=f"symbol_reference ({relation})",
                    confidence=confidence,
                )
                related.append(seen[key])
        return related
