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
   frame's path doesn't map into the clone, and the error-signature text.
   The signature is grepped as a *log template*, not a rendered message:
   runtime data (numbers, durations, UUIDs, quoted values, paths) is
   stripped first, because source contains the format string, never the
   rendered value — "connection pool exhausted after 5000ms" can only match
   as "connection pool exhausted". Three descending-confidence passes:
   static literal (0.7), exception class raise/definition site (0.55),
   identifier co-occurrence (0.4). All grep passes run over every searchable
   text file in the clone — a Go/TS/Java repo must not get zero candidates
   just because the AST passes are Python-only;
3. symbol references — one hop outward from the primaries along the call
   graph (callers and callees defined in this repo), so the diagnosis
   prompt carries the failing function's neighbourhood, not just the frame
   the exception surfaced in.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from haaland.domain.models import CodeLocation, FailureTrace, TraceFrame
from haaland.services.code_toolbox import iter_searchable
from haaland.services.workspace_service import Workspace

_TRACEBACK_FRAME = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\S+))?')
_MAX_PRIMARY = 8
_MAX_RELATED = 4
_CONTEXT_LINES = 6
# Per-pass ceilings for the grep fallbacks, so a common phrase can't flood
# the candidate set before ranking.
_MAX_LITERAL_MATCHES = 6
_MAX_CLASS_MATCHES = 4
_MAX_COOCCURRENCE_MATCHES = 4


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


def build_failure_trace(log_text: str) -> FailureTrace:
    """The structured form of what `extract_call_chain` returns as bare
    names: every frame with its path and line, plus the error signature the
    traceback terminated in.

    Persisted as a `trace` evidence row by the locate_code node so the
    dashboard can render the failure path. Deliberately derived here rather
    than in the node: the deterministic pass already parses all of it to
    rank candidates, so this is a second read of the same log, not a second
    source of truth.
    """
    exception_class, exception_message = extract_error_signature(log_text)
    return FailureTrace(
        call_chain=extract_call_chain(log_text),
        # Unlike the call chain, `<module>` frames are kept: the chain is the
        # workflow, these are the literal traceback, and dropping frames here
        # would silently renumber the depths the ordering depends on.
        frames=[
            TraceFrame(depth=depth, path=path, line=line, function=func)
            for depth, (path, line, func) in enumerate(parse_traceback_frames(log_text))
        ],
        exception_class=exception_class,
        exception_message=exception_message,
    )


def extract_error_signature(log_text: str) -> tuple[str | None, str | None]:
    """The last 'SomeError: message' style line, if any — a decent proxy for
    the error signature grouping docs/04 describes for the Loki adapter.
    Returns (exception_class, message); either may be None."""
    lines = [line.strip() for line in log_text.strip().splitlines() if line.strip()]
    pattern = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b:?\s*(.*)")
    for line in reversed(lines):
        m = pattern.search(line)
        if m:
            return m.group(1), m.group(2).strip() or None
    return None, None


# Runtime data inside a rendered log message — never present in source, which
# carries the format string. Stripped before grepping so the needle is the
# log *template*, not the rendered value.
_VARIABLE_PART = re.compile(
    r"""
      '[^']*' | "[^"]*"                                     # quoted values
    | \b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}
       -[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b                    # UUIDs
    | \b0x[0-9a-fA-F]+\b                                    # hex ids
    | (?:[A-Za-z]:)?(?:[\\/][\w.\-]+){2,}                   # filesystem paths
    | \b\d+(?:[.,]\d+)*\s*
       (?:ms|s|sec|secs|seconds|m|min|mins|minutes|h|hrs|hours
        |%|b|kb|mb|gb|tb|kib|mib|gib)?\b                    # numbers + units
    """,
    re.VERBOSE | re.IGNORECASE,
)

_IDENTIFIER_STOPWORDS = frozenset(
    {"after", "with", "from", "this", "that", "when", "while", "error", "exception",
     "failed", "failure", "unable", "could", "cannot", "during", "because", "invalid",
     "unexpected", "internal", "request", "response"}
)


def _static_literal(message: str) -> str | None:
    """The longest static run of the message once variable parts are
    stripped — the piece most likely to appear verbatim in the source's
    format string."""
    runs = [
        run.strip(" \t.,:;!?()[]{}<>=-")
        for run in _VARIABLE_PART.sub("\x00", message).split("\x00")
    ]
    runs = [r for r in runs if len(r) >= 12 or len(r.split()) >= 3]
    if not runs:
        return None
    return max(runs, key=len)[:80]


def _identifier_terms(message: str) -> list[str]:
    """Domain-identifier-ish words from the message (e.g. pool, timeout,
    connection) for the lowest-confidence co-occurrence pass."""
    words = re.findall(r"[A-Za-z_]{4,}", message.lower())
    seen: list[str] = []
    for w in words:
        if w not in _IDENTIFIER_STOPWORDS and w not in seen:
            seen.append(w)
    return seen[:6]


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
    for rel, _path in iter_searchable(workspace):
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

        exc_class, message = extract_error_signature(log_text)
        self._grep_error_template(workspace, exc_class, message, candidates)

        primaries = sorted(candidates.values(), key=lambda c: c.confidence, reverse=True)[:_MAX_PRIMARY]
        related = self._expand_symbol_references(workspace, index, primaries, candidates)
        return primaries + related

    def _grep_error_template(
        self,
        workspace: Workspace,
        exc_class: str | None,
        message: str | None,
        candidates: dict[tuple[str, int, int], CodeLocation],
    ) -> None:
        """Three descending-confidence passes over every searchable text file
        (not just Python — the AST passes are Python-gated, these are not):

        1. the message's longest static literal run, runtime data stripped
           (source holds the format string, never the rendered value) — 0.7;
        2. the exception class at a raise/definition/construction site — 0.55;
        3. lines where >= 2 identifier terms from the message co-occur — 0.4.
        """
        literal = _static_literal(message) if message else None
        terms = _identifier_terms(message) if message else []

        class_rx = None
        if exc_class:
            # Raise/definition/construction sites only — a bare mention of a
            # builtin like TimeoutError would match half the codebase.
            escaped = re.escape(exc_class)
            class_rx = re.compile(
                rf"(?:\braise\s+(?:\w+\.)*{escaped}\b"
                rf"|\bclass\s+{escaped}\b"
                rf"|\b(?:throw|panic|errors\.New)\b.*\b{escaped}\b"
                rf"|\b{escaped}\s*\()"
            )

        found = {"literal": 0, "class": 0, "cooccur": 0}
        for rel_path, _path in iter_searchable(workspace):
            if all(
                found[k] >= cap
                for k, cap in (
                    ("literal", _MAX_LITERAL_MATCHES),
                    ("class", _MAX_CLASS_MATCHES),
                    ("cooccur", _MAX_COOCCURRENCE_MATCHES),
                )
            ):
                return
            content = workspace.read_file(rel_path) or ""
            for line_no, line in enumerate(content.splitlines(), start=1):
                if literal and found["literal"] < _MAX_LITERAL_MATCHES and literal in line:
                    self._add_grep_candidate(
                        workspace, candidates, rel_path, line_no, "error_signature_grep", 0.7
                    )
                    found["literal"] += 1
                elif class_rx and found["class"] < _MAX_CLASS_MATCHES and class_rx.search(line):
                    self._add_grep_candidate(
                        workspace, candidates, rel_path, line_no, "exception_class_grep", 0.55
                    )
                    found["class"] += 1
                elif (
                    len(terms) >= 2
                    and found["cooccur"] < _MAX_COOCCURRENCE_MATCHES
                    and sum(t in line.lower() for t in terms) >= 2
                ):
                    self._add_grep_candidate(
                        workspace, candidates, rel_path, line_no, "identifier_cooccurrence_grep", 0.4
                    )
                    found["cooccur"] += 1

    @staticmethod
    def _add_grep_candidate(
        workspace: Workspace,
        candidates: dict[tuple[str, int, int], CodeLocation],
        rel_path: str,
        line_no: int,
        reason: str,
        confidence: float,
    ) -> None:
        start, end = max(1, line_no - _CONTEXT_LINES), line_no + _CONTEXT_LINES
        key = (rel_path, start, end)
        existing = candidates.get(key)
        if existing is not None and existing.confidence >= confidence:
            return
        candidates[key] = CodeLocation(
            path=rel_path,
            start_line=start,
            end_line=end,
            snippet=_snippet(workspace, rel_path, start, end),
            reason=reason,
            confidence=confidence,
        )

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
