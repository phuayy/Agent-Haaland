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
