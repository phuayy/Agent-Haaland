"""Exercises the Stage 1 workhorse against the exact traceback shape
demo/seed_repo/error.log carries, without needing a git clone — locate()
only reads files off disk (see services/code_search_service.py)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from haaland.services.code_search_service import CodeSearchService
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
