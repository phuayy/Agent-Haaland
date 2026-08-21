"""Progress pings — the short "still working" cards that fill the silence
between an incident being accepted and its post-mortem landing.

Why this is a separate concept from the notifications the graph already
sends: every one of those (triaged_low, approval_requested, escalated,
incident_closed, and the crash page in tasks/debug_session.py) is an
*outcome* someone has to act on. A real run clones a repo, explores it with
an agentic tool loop, drafts a patch and puts it through static checks and
tests — minutes during which the channel sees nothing at all. The first
card a human reads is then a PR review request for an incident they never
saw start.

Three rules keep these from becoming the noise that gets a bot muted:

- Milestones, not nodes. The graph has seventeen nodes; there are three
  pings, one per phase a human would name out loud.
- No call to action. No buttons, no mentions — a progress card is a
  heartbeat, and a button on it competes for the eye with the two cards
  that genuinely need a click.
- Once each. The fix loop re-enters `evaluate_fixes` on every retry and on
  a human rejection; the "debugging" ping fires on the first attempt only
  (see agent/nodes/evaluate_fixes.py), so a three-attempt run still posts
  exactly one.

Pure functions: this module decides what a ping *says*. Sending it — and
the best-effort failure handling that goes with it — is
agent/nodes/_progress.py, because delivery needs a DB session for the
audit row and services/ owns no session."""

from __future__ import annotations

from typing import Literal

from haaland.domain.enums import Severity
from haaland.domain.models import NotificationMessage

#: The milestones, in the order a run passes them. Extending this is a
#: deliberate act — every entry added is another card in someone's chat.
ProgressStage = Literal["accepted", "diagnosing", "fixing"]

#: stage -> (card title, what happens next). The title is what a reader
#: skimming the chat takes in; the line is what they get if they stop. Both
#: are written to be true even when the stage turns out to be the last one
#: the run reaches — none of them promises a fix.
_STAGES: dict[ProgressStage, tuple[str, str]] = {
    "accepted": (
        "Request accepted",
        "Logs received, run started. The next update lands when a root cause "
        "is identified.",
    ),
    "diagnosing": (
        "Diagnosing",
        "Repository cloned. Reading the code to locate the root cause.",
    ),
    "fixing": (
        "Debugging",
        "Drafting a patch and putting it through static checks and tests. "
        "Nothing is pushed until they pass.",
    ),
}


def progress_message(
    stage: ProgressStage,
    *,
    reference: str,
    service_name: str,
    severity: Severity | None = None,
    detail: str | None = None,
) -> NotificationMessage:
    """One milestone as a channel-agnostic message.

    `detail` is an already-formatted markdown line (e.g.
    `"**Root cause:** ..."`) that the calling node has context for and this
    module does not; it is rendered above the stage line, or omitted."""
    title, line = _STAGES[stage]
    body = [f"**Service:** {service_name}"]
    if detail:
        body.append(detail)
    body.extend(["", line])

    return NotificationMessage(
        kind="progress",
        title=f"[{reference}] {title}",
        body_markdown="\n".join(body),
        incident_reference=reference,
        severity=severity,
        # links and mentions deliberately empty — see the module docstring.
    )
