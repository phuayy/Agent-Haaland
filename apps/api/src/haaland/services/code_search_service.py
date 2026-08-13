"""Stage 1's deterministic half. Turns a stack trace and an error message
into ranked file:line candidates *before* the model reasons about them —
the model then explains and selects among candidates we already located,
rather than being asked to find a needle in an entire repository (docs/04's
"never paste an entire repository into a prompt" principle, applied to
source code instead of logs)."""

from __future__ import annotations

import ast
import re

from haaland.domain.models import CodeLocation
from haaland.services.workspace_service import Workspace

_TRACEBACK_FRAME = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\S+))?')
_MAX_CANDIDATES = 8
_CONTEXT_LINES = 6


def parse_traceback_frames(log_text: str) -> list[tuple[str, int, str | None]]:
    return [(m.group(1), int(m.group(2)), m.group(3)) for m in _TRACEBACK_FRAME.finditer(log_text)]


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
        candidates: dict[tuple[str, int, int], CodeLocation] = {}

        frames = parse_traceback_frames(log_text)
        for depth, (raw_path, line, _func) in enumerate(frames):
            rel_path = _relative_path(workspace, raw_path)
            if rel_path is None:
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

        ranked = sorted(candidates.values(), key=lambda c: c.confidence, reverse=True)
        return ranked[:_MAX_CANDIDATES]
