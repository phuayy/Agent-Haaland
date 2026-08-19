"""Exercises the Stage 1 workhorse against the exact traceback shape
demo/seed_repo/error.log carries, without needing a git clone — locate()
only reads files off disk (see services/code_search_service.py)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from haaland.services.code_search_service import CodeSearchService, extract_call_chain
from haaland.services.workspace_service import Workspace

_PRICING_SOURCE = '''"""Order pricing helpers for the seed 'orders-api' service."""

from __future__ import annotations


def average_item_price(items: list[dict]) -> float:
    total = sum(item["price"] for item in items)
    return total / len(items)


def apply_discount(items: list[dict], discount_pct: float) -> float:
    avg_price = average_item_price(items)
    return avg_price * (1 - discount_pct / 100)
'''

_LOG_TEXT = (
    "ERROR orders-api Unhandled exception in /orders/quote\n"
    "Traceback (most recent call last):\n"
    '  File "/app/app/main.py", line 11, in quote\n'
    "    return apply_discount(items, discount_pct)\n"
    '  File "/app/app/pricing.py", line 12, in apply_discount\n'
    "    avg_price = average_item_price(items)\n"
    '  File "/app/app/pricing.py", line 8, in average_item_price\n'
    "    return total / len(items)\n"
    "ZeroDivisionError: division by zero\n"
)


def _workspace(tmp_path: Path) -> Workspace:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "pricing.py").write_text(_PRICING_SOURCE, encoding="utf-8")
    return Workspace(incident_id=uuid4(), path=tmp_path, base_sha="deadbeef", repo=None)


def test_locates_the_traceback_frame(tmp_path):
    workspace = _workspace(tmp_path)
    candidates = CodeSearchService().locate(workspace, _LOG_TEXT)

    assert candidates, "expected at least one candidate"
    top = candidates[0]
    assert top.path == "app/pricing.py"
    assert top.reason == "traceback_frame"
    assert top.start_line <= 8 <= top.end_line
    assert "return total / len(items)" in top.snippet


def test_traceback_frame_ranks_above_signature_grep(tmp_path):
    workspace = _workspace(tmp_path)
    candidates = CodeSearchService().locate(workspace, _LOG_TEXT)

    reasons = [c.reason for c in candidates]
    if "error_signature_grep" in reasons:
        traceback_idx = reasons.index("traceback_frame")
        grep_idx = reasons.index("error_signature_grep")
        assert traceback_idx < grep_idx


def test_no_candidates_when_traceback_does_not_match_repo(tmp_path):
    workspace = _workspace(tmp_path)
    unrelated_log = 'File "/somewhere/else/unrelated.py", line 3, in foo\nKeyError: x'
    candidates = CodeSearchService().locate(workspace, unrelated_log)

    assert all(c.reason != "traceback_frame" for c in candidates)


def test_function_name_grep_when_frame_path_does_not_map(tmp_path):
    """A traceback from a container layout the clone doesn't mirror still
    names the failing function — the definition must be grepped instead of
    the frame being dropped."""
    workspace = _workspace(tmp_path)
    log = (
        "Traceback (most recent call last):\n"
        '  File "/srv/deployed/elsewhere.py", line 8, in average_item_price\n'
        "    return total / len(items)\n"
        "ZeroDivisionError: division by zero\n"
    )
    candidates = CodeSearchService().locate(workspace, log)

    grepped = [c for c in candidates if c.reason == "function_name_grep"]
    assert grepped, "expected a function_name_grep candidate"
    assert grepped[0].path == "app/pricing.py"
    assert "def average_item_price" in grepped[0].snippet


def test_symbol_references_expand_to_callers_outside_the_traceback(tmp_path):
    """`build_report` calls the failing `average_item_price` but never
    appears in the traceback; one hop of call-graph expansion must surface
    it as a related candidate ranked below every primary. Callers that are
    already traceback primaries must NOT be duplicated as symbol refs."""
    workspace = _workspace(tmp_path)
    (tmp_path / "app" / "reports.py").write_text(
        "from app.pricing import average_item_price\n\n\n"
        "def build_report(items: list[dict]) -> float:\n"
        "    return average_item_price(items) * 2\n",
        encoding="utf-8",
    )
    candidates = CodeSearchService().locate(workspace, _LOG_TEXT)

    related = [c for c in candidates if c.reason.startswith("symbol_reference")]
    assert any(
        "caller of average_item_price" in c.reason and "def build_report" in c.snippet
        for c in related
    ), f"expected build_report as caller, got: {[c.reason for c in candidates]}"

    primaries = [c for c in candidates if not c.reason.startswith("symbol_reference")]
    primary_spans = {(c.path, c.start_line) for c in primaries}
    assert all((r.path, r.start_line) not in primary_spans for r in related)
    assert all(r.confidence < min(c.confidence for c in primaries) for r in related)


def test_extract_call_chain_orders_outermost_first():
    assert extract_call_chain(_LOG_TEXT) == ["quote", "apply_discount", "average_item_price"]


def test_extract_call_chain_ignores_module_frames():
    log = '  File "/app/x.py", line 1, in <module>\n  File "/app/y.py", line 2, in handler\n'
    assert extract_call_chain(log) == ["handler"]
