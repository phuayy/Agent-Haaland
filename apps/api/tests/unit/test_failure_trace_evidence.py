"""The `trace` evidence row's payload shape.

The invariant worth a test is the redaction one: the exception message is
rendered runtime data and must reach the row through the redaction choke
point, never straight off the parsed trace (agent/nodes/locate_code.py).
"""

from __future__ import annotations

from haaland.agent.nodes.locate_code import _trace_content
from haaland.services.code_search_service import build_failure_trace

_LOG_TEXT = (
    "Traceback (most recent call last):\n"
    '  File "/app/api/routes.py", line 42, in quote\n'
    '  File "/app/workers/pricing.py", line 8, in average_item_price\n'
    "ValueError: no price for account alice@example.com\n"
)


def test_trace_content_carries_frames_in_depth_order():
    content = _trace_content(build_failure_trace(_LOG_TEXT), None)

    assert [f["depth"] for f in content["frames"]] == [0, 1]
    assert [f["function"] for f in content["frames"]] == ["quote", "average_item_price"]
    assert content["call_chain"] == ["quote", "average_item_price"]
    assert content["exception_class"] == "ValueError"


def test_trace_content_stores_the_redacted_message_not_the_raw_one():
    trace = build_failure_trace(_LOG_TEXT)
    assert "alice@example.com" in (trace.exception_message or "")

    content = _trace_content(trace, "no price for account <EMAIL_1>")

    assert content["exception_message"] == "no price for account <EMAIL_1>"
    assert "alice@example.com" not in str(content)


def test_trace_content_message_is_none_when_nothing_was_redacted():
    """A traceback with no message line must not invent an empty string —
    the frontend distinguishes 'no message' from 'blank message'."""
    trace = build_failure_trace('  File "/app/x.py", line 1, in handler\n')

    content = _trace_content(trace, None)

    assert content["exception_message"] is None
    assert content["exception_class"] is None
