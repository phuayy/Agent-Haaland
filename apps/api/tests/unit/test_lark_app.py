from __future__ import annotations

import base64
import hashlib
import json
import time
from types import SimpleNamespace

import httpx
import pytest
import respx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import FastAPI
from fastapi.testclient import TestClient

from haaland.api.webhooks.signature import verify_lark_signature
from haaland.domain.models import NotificationMessage
from haaland.integrations.notify.lark import LarkAPIError, LarkAppClient, LarkAppNotifier
from haaland.integrations.notify.lark.app_bot import infer_receive_id_type
from haaland.integrations.notify.lark.crypto import LarkDecryptionError, decrypt_payload

_BASE = "https://open.larksuite.com"
_TOKEN_URL = f"{_BASE}/open-apis/auth/v3/tenant_access_token/internal"
_MESSAGES_URL = f"{_BASE}/open-apis/im/v1/messages"
_CHATS_URL = f"{_BASE}/open-apis/im/v1/chats"


def _client() -> LarkAppClient:
    return LarkAppClient("cli_app", "s3cret", domain="global")


def _token_response(token: str = "t-abc", expire: int = 7200) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "tenant_access_token": token, "expire": expire})


def _message(**overrides) -> NotificationMessage:
    defaults = dict(
        kind="approval_requested",
        title="[INC-2026-0001] Fix drafted — review required",
        body_markdown="**Root cause:** pool exhausted",
        incident_reference="INC-2026-0001",
        severity="P1",
    )
    defaults.update(overrides)
    return NotificationMessage(**defaults)


def test_unknown_domain_is_rejected_at_construction():
    with pytest.raises(ValueError, match="unknown lark domain"):
        LarkAppClient("cli_app", "s3cret", domain="example.com")


@respx.mock
async def test_token_is_exchanged_once_and_cached():
    token_route = respx.post(_TOKEN_URL).mock(return_value=_token_response())
    respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})
    )
    client = _client()

    await client.send_card("oc_chat", {"elements": []})
    await client.send_card("oc_chat", {"elements": []})

    assert token_route.call_count == 1


@respx.mock
async def test_send_card_encodes_content_as_a_json_string():
    respx.post(_TOKEN_URL).mock(return_value=_token_response())
    route = respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"message_id": "om_42"}})
    )

    message_id = await LarkAppNotifier(_client(), "oc_chat").send(_message())

    assert message_id == "om_42"
    request = route.calls.last.request
    assert request.url.params["receive_id_type"] == "chat_id"
    assert request.headers["authorization"] == "Bearer t-abc"
    body = json.loads(request.content)
    assert body["msg_type"] == "interactive"
    # `content` must be a serialised string, not a nested object — Lark
    # rejects the object form with code 230001.
    assert isinstance(body["content"], str)
    assert json.loads(body["content"])["header"]["template"] == "red"


@respx.mock
async def test_expired_token_is_refreshed_and_the_call_retried_once():
    respx.post(_TOKEN_URL).mock(
        side_effect=[_token_response("t-stale"), _token_response("t-fresh")]
    )
    route = respx.post(_MESSAGES_URL).mock(
        side_effect=[
            httpx.Response(200, json={"code": 99991663, "msg": "token expired"}),
            httpx.Response(200, json={"code": 0, "data": {"message_id": "om_7"}}),
        ]
    )

    assert await _client().send_card("oc_chat", {"elements": []}) == "om_7"
    assert route.call_count == 2
    assert route.calls.last.request.headers["authorization"] == "Bearer t-fresh"


@respx.mock
async def test_application_error_is_not_retried_and_carries_the_code():
    respx.post(_TOKEN_URL).mock(return_value=_token_response())
    route = respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(200, json={"code": 230002, "msg": "bot is not in the chat"})
    )

    with pytest.raises(LarkAPIError) as exc_info:
        await _client().send_card("oc_missing", {"elements": []})

    assert exc_info.value.code == 230002
    assert route.call_count == 1


@respx.mock
async def test_list_chats_projects_the_fields_an_operator_needs():
    respx.post(_TOKEN_URL).mock(return_value=_token_response())
    respx.get(_CHATS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"items": [{"chat_id": "oc_1", "name": "SRE", "description": "", "avatar": "x"}]},
            },
        )
    )

    chats = await _client().list_chats()

    assert chats == [{"chat_id": "oc_1", "name": "SRE", "description": ""}]


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("oc_abc", "chat_id"),
        ("ou_abc", "open_id"),
        ("on_abc", "union_id"),
        ("dev@acme.com", "email"),
        ("something-else", "chat_id"),
    ],
)
def test_receive_id_type_is_inferred_from_the_lark_id_prefix(target, expected):
    assert infer_receive_id_type(target, "chat_id") == expected


@respx.mock
async def test_message_target_overrides_the_configured_default():
    respx.post(_TOKEN_URL).mock(return_value=_token_response())
    route = respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"message_id": "om_9"}})
    )

    await LarkAppNotifier(_client(), "oc_default").send(_message(target="dev@acme.com"))

    request = route.calls.last.request
    assert request.url.params["receive_id_type"] == "email"
    assert json.loads(request.content)["receive_id"] == "dev@acme.com"


# --------------------------------------------------------------- callbacks


def _encrypt(encrypt_key: str, plaintext: str) -> str:
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = b"0123456789abcdef"
    padding = 16 - len(plaintext.encode()) % 16
    padded = plaintext.encode() + bytes([padding]) * padding
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(iv + encryptor.update(padded) + encryptor.finalize()).decode()


def test_callback_signature_round_trip():
    encrypt_key, nonce = "enc-key", "n0nce"
    timestamp = str(int(time.time()))
    body = b'{"encrypt":"..."}'
    signature = hashlib.sha256(
        timestamp.encode() + nonce.encode() + encrypt_key.encode() + body
    ).hexdigest()

    assert verify_lark_signature(encrypt_key, timestamp, nonce, body, signature)
    assert not verify_lark_signature(encrypt_key, timestamp, nonce, body + b"x", signature)
    assert not verify_lark_signature("other-key", timestamp, nonce, body, signature)
    assert not verify_lark_signature(None, timestamp, nonce, body, signature)


def test_callback_signature_rejects_a_replayed_timestamp():
    encrypt_key, nonce = "enc-key", "n0nce"
    timestamp = str(int(time.time()) - 600)
    body = b"{}"
    signature = hashlib.sha256(
        timestamp.encode() + nonce.encode() + encrypt_key.encode() + body
    ).hexdigest()

    assert not verify_lark_signature(encrypt_key, timestamp, nonce, body, signature)


def test_encrypted_payload_round_trip():
    plaintext = json.dumps({"type": "url_verification", "challenge": "c-1"})
    assert decrypt_payload("enc-key", _encrypt("enc-key", plaintext)) == plaintext


def test_decryption_with_the_wrong_key_raises_rather_than_returning_garbage():
    encrypted = _encrypt("enc-key", json.dumps({"challenge": "c-1"}))
    with pytest.raises(LarkDecryptionError):
        decrypt_payload("wrong-key", encrypted)


def _callback_client(**settings_overrides) -> TestClient:
    from haaland.api.deps import get_deps
    from haaland.api.webhooks import lark as lark_webhook
    from haaland.config import Settings

    settings = Settings(llm_provider="fake", **settings_overrides)
    app = FastAPI()
    app.include_router(lark_webhook.router)
    app.dependency_overrides[get_deps] = lambda: SimpleNamespace(settings=settings)
    return TestClient(app, raise_server_exceptions=False)


def _signed_headers(encrypt_key: str, body: bytes) -> dict[str, str]:
    timestamp, nonce = str(int(time.time())), "n0nce"
    signature = hashlib.sha256(
        timestamp.encode() + nonce.encode() + encrypt_key.encode() + body
    ).hexdigest()
    return {
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
        "Content-Type": "application/json",
    }


def test_callback_endpoint_is_503_until_configured():
    resp = _callback_client().post("/webhooks/lark/card", json={"type": "url_verification"})
    assert resp.status_code == 503


def test_plaintext_challenge_is_echoed_back():
    client = _callback_client(lark_verification_token="v-token")

    resp = client.post(
        "/webhooks/lark/card",
        json={"type": "url_verification", "challenge": "c-1", "token": "v-token"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"challenge": "c-1"}


def test_challenge_with_the_wrong_verification_token_is_rejected():
    client = _callback_client(lark_verification_token="v-token")

    resp = client.post(
        "/webhooks/lark/card",
        json={"type": "url_verification", "challenge": "c-1", "token": "not-it"},
    )

    assert resp.status_code == 401


def test_encrypted_challenge_is_verified_decrypted_and_echoed():
    encrypt_key = "enc-key"
    client = _callback_client(lark_encrypt_key=encrypt_key, lark_verification_token="v-token")
    inner = json.dumps({"type": "url_verification", "challenge": "c-2", "token": "v-token"})
    body = json.dumps({"encrypt": _encrypt(encrypt_key, inner)}).encode()

    resp = client.post("/webhooks/lark/card", content=body, headers=_signed_headers(encrypt_key, body))

    assert resp.status_code == 200
    assert resp.json() == {"challenge": "c-2"}


def test_encrypted_callback_with_a_bad_signature_is_rejected_before_decryption():
    encrypt_key = "enc-key"
    client = _callback_client(lark_encrypt_key=encrypt_key, lark_verification_token="v-token")
    body = json.dumps({"encrypt": _encrypt(encrypt_key, "{}")}).encode()
    headers = _signed_headers(encrypt_key, body) | {"X-Lark-Signature": "0" * 64}

    resp = client.post("/webhooks/lark/card", content=body, headers=headers)

    assert resp.status_code == 401


def test_card_action_reports_501_rather_than_silently_dropping_the_tap():
    client = _callback_client(lark_verification_token="v-token")

    resp = client.post(
        "/webhooks/lark/card",
        json={"token": "v-token", "action": {"value": {"action": "approve_remediation"}}},
    )

    assert resp.status_code == 501
