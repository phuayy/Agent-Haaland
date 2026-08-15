"""Lark (Feishu) custom-bot webhook adapter.

Setup on the Lark side: in the target group chat, Settings -> Bots ->
Add Bot -> Custom Bot. Copy the webhook URL into HAALAND_LARK_WEBHOOK_URL.
If "Signature verification" is enabled on the bot, copy its secret into
HAALAND_LARK_WEBHOOK_SECRET — the signing scheme is Lark's documented
quirk: base64(HMAC-SHA256(key="{timestamp}\\n{secret}", message="")).

Messages are sent as interactive cards: colour-coded severity header,
incident facts, and buttons linking to the PR and the incident. Raw
httpx, no SDK — it is a single POST (docs/02's "three endpoints do not
justify an SDK" rule applies at n=1)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import httpx

from haaland.domain.models import NotificationMessage
from haaland.integrations.base import NotificationError

_HEADER_TEMPLATE_BY_SEVERITY = {"P1": "red", "P2": "orange", "P3": "yellow", "P4": "grey"}
_HEADER_TEMPLATE_BY_KIND = {
    "approval_requested": "orange",
    "incident_closed": "green",
    "escalated": "red",
    "test": "blue",
}


def lark_sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


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


class LarkNotifier:
    name = "lark"

    def __init__(self, webhook_url: str, secret: str | None = None, *, timeout_seconds: float = 10):
        self._webhook_url = webhook_url
        self._secret = secret
        self._timeout = timeout_seconds

    def _payload(self, message: NotificationMessage) -> dict:
        payload: dict = {"msg_type": "interactive", "card": build_card(message)}
        if self._secret:
            timestamp = int(time.time())
            payload["timestamp"] = str(timestamp)
            payload["sign"] = lark_sign(self._secret, timestamp)
        return payload

    async def send(self, message: NotificationMessage) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._webhook_url, json=self._payload(message))
        except httpx.HTTPError as exc:
            raise NotificationError(f"lark webhook unreachable: {exc}") from exc

        if resp.status_code != 200:
            raise NotificationError(f"lark webhook HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        # Lark returns {"code": 0, ...} on success; non-zero code is an
        # application-level rejection (bad sign, keyword filter, ...).
        if body.get("code", body.get("StatusCode", 0)) != 0:
            raise NotificationError(f"lark rejected the message: {body}")
        return str(body.get("data", {}).get("message_id", "") or f"lark-{int(time.time())}")
