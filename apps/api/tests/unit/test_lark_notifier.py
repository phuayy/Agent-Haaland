from __future__ import annotations

import base64
import hashlib
import hmac

import httpx
import pytest
import respx

from haaland.domain.models import NotificationMessage
from haaland.integrations.base import NotificationError
from haaland.integrations.notify.lark import LarkNotifier, build_card, lark_sign

_WEBHOOK = "https://open.larksuite.com/open-apis/bot/v2/hook/test-hook-id"


def _message(**overrides) -> NotificationMessage:
    defaults = dict(
        kind="approval_requested",
        title="[INC-2026-0001] Fix drafted — review required",
        body_markdown="**Root cause:** pool exhausted",
        incident_reference="INC-2026-0001",
        severity="P1",
        links={"Review PR": "https://github.com/acme/x/pull/1"},
        mentions=["alice"],
    )
    defaults.update(overrides)
    return NotificationMessage(**defaults)


def test_lark_sign_matches_documented_scheme():
    """Lark's quirk: HMAC key is '{timestamp}\\n{secret}', message is empty."""
    secret, timestamp = "s3cret", 1755230000
    expected = base64.b64encode(
        hmac.new(f"{timestamp}\n{secret}".encode(), digestmod=hashlib.sha256).digest()
    ).decode()
    assert lark_sign(secret, timestamp) == expected


def test_card_reflects_severity_and_links():
    card = build_card(_message())
    assert card["header"]["template"] == "red"  # P1
    assert "INC-2026-0001" in card["elements"][0]["content"]
    buttons = card["elements"][-1]["actions"]
    assert buttons[0]["url"] == "https://github.com/acme/x/pull/1"


@pytest.mark.parametrize(
    ("severity", "template"), [("P1", "red"), ("P2", "orange"), ("P3", "yellow"), ("P4", "grey")]
)
def test_every_severity_band_renders_a_card(severity, template):
    """P3/P4 are notified too, not just the paging bands — the low path
    files a ticket and still posts a card (agent/nodes/file_ticket.py)."""
    card = build_card(_message(kind="triaged_low", severity=severity))
    assert card["header"]["template"] == template
    assert f"**Severity:** {severity}" in card["elements"][0]["content"]


@pytest.mark.parametrize(
    ("kind", "severity", "template"),
    [("incident_closed", "P1", "green"), ("escalated", "P4", "red")],
)
def test_terminal_outcome_colour_beats_the_severity_band(kind, severity, template):
    """A resolved P1 is not an emergency and a run that died on a P4 is not
    routine — once an incident is over, the outcome is what the channel
    sorts on. The band is still spelled out in the facts line."""
    card = build_card(_message(kind=kind, severity=severity))
    assert card["header"]["template"] == template
    assert f"**Severity:** {severity}" in card["elements"][0]["content"]


def test_card_falls_back_to_kind_colour_without_severity():
    card = build_card(_message(severity=None, kind="incident_closed"))
    assert card["header"]["template"] == "green"


@respx.mock
async def test_send_success_with_signature():
    route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200, json={"code": 0}))
    notifier = LarkNotifier(_WEBHOOK, secret="s3cret")

    ref = await notifier.send(_message())

    assert ref
    sent = route.calls.last.request
    import json

    payload = json.loads(sent.content)
    assert payload["msg_type"] == "interactive"
    assert payload["sign"] == lark_sign("s3cret", int(payload["timestamp"]))


@respx.mock
async def test_send_raises_on_application_level_rejection():
    respx.post(_WEBHOOK).mock(
        return_value=httpx.Response(200, json={"code": 19021, "msg": "sign match fail"})
    )
    with pytest.raises(NotificationError, match="rejected"):
        await LarkNotifier(_WEBHOOK, secret="wrong").send(_message())


@respx.mock
async def test_send_raises_on_http_error():
    respx.post(_WEBHOOK).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(NotificationError, match="HTTP 500"):
        await LarkNotifier(_WEBHOOK).send(_message())
