"""Lark interactive-card rendering — the one place a `NotificationMessage`
becomes Lark's card schema.

Deliberately shared by both transports (`webhook_bot.py`, `app_bot.py`):
the custom-bot webhook and the tenant application differ in *how* a card is
delivered and authenticated, never in what the card looks like. Keeping the
rendering here means a card change is reviewed once and both transports move
together.

Pure functions, no I/O — so card layout is unit-testable without a network
mock (see tests/unit/test_lark_notifier.py)."""

from __future__ import annotations

from haaland.domain.models import NotificationMessage

_HEADER_TEMPLATE_BY_SEVERITY = {"P1": "red", "P2": "orange", "P3": "yellow", "P4": "grey"}
_HEADER_TEMPLATE_BY_KIND = {
    "approval_requested": "orange",
    "incident_closed": "green",
    "escalated": "red",
    "triaged_low": "grey",
    "progress": "blue",
    "test": "blue",
}
# Terminal-outcome cards take their colour from the outcome, not from the
# severity band: a resolved P1 is green and a run that died on a P4 is red,
# because by then the outcome is what the channel needs to sort on. In-flight
# cards keep the severity colour so urgency is what stands out while the
# incident is still moving. The band is always spelled out in the facts line
# either way, so nothing is lost by not colouring it.
_OUTCOME_KINDS = frozenset({"incident_closed", "escalated"})
# Progress pings ignore the severity colour for the opposite reason: a
# heartbeat wearing a P1's red teaches the channel to read urgency into a
# card that asks for nothing. They are always the calm blue.
_KIND_COLOURED = _OUTCOME_KINDS | {"progress"}


def build_card(message: NotificationMessage) -> dict:
    if message.kind in _KIND_COLOURED:
        template = _HEADER_TEMPLATE_BY_KIND[message.kind]
    else:
        template = (
            _HEADER_TEMPLATE_BY_SEVERITY.get(message.severity.value)
            if message.severity
            else None
        ) or _HEADER_TEMPLATE_BY_KIND.get(message.kind, "blue")

    elements: list[dict] = [
        {"tag": "markdown", "content": message.body_markdown},
    ]

    facts = []
    if message.incident_reference:
        facts.append(f"**Incident:** {message.incident_reference}")
    if message.severity:
        facts.append(f"**Severity:** {message.severity.value}")
    if message.mentions:
        facts.append("**Reviewers:** " + ", ".join(message.mentions))
    if facts:
        elements.insert(0, {"tag": "markdown", "content": "\n".join(facts)})

    if message.links:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": label},
                        "type": "primary" if label.lower().startswith("review") else "default",
                        "url": url,
                    }
                    for label, url in message.links.items()
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": message.title},
        },
        "elements": elements,
    }
