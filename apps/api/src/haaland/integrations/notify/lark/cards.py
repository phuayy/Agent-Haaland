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
    "test": "blue",
}


def build_card(message: NotificationMessage) -> dict:
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
