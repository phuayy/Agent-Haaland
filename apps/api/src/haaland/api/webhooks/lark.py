"""Inbound Lark callbacks — the endpoint the Lark application's "Request
URL" points at.

Two things arrive here. Lark's **URL verification challenge**, which the
Lark console fires when you save the Request URL and which must be echoed
back or the app cannot be configured at all; and **card action callbacks**
(an Approve/Reject tap). Only the first is implemented: the approval flow
behind a card tap needs a `users.lark_open_id` mapping, role
authorisation and an `approvals` row (docs/11 §4), none of which exist yet,
and a button that silently does nothing is worse than one that reports 501.
Approve/reject over HTTP (`POST /api/incidents/{ref}/approve`) is the
supported path today.

Verification still runs first and for real, in the order docs/04 mandates:
verify the signature against the raw bytes, then decrypt, then parse."""

from __future__ import annotations

import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from haaland.api.deps import get_deps
from haaland.api.webhooks.signature import verify_lark_signature
from haaland.integrations.notify.lark.crypto import LarkDecryptionError, decrypt_payload

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _decoded_payload(settings, headers, raw_body: bytes) -> dict:
    """Signature check -> decrypt -> parse. An Encrypt Key is what makes the
    callback verifiable, so when one is configured an unsigned or badly
    signed request is rejected outright; without one, Lark sends plaintext
    and the shared verification token is the only available check."""
    if settings.lark_encrypt_key and not verify_lark_signature(
        settings.lark_encrypt_key,
        headers.get("x-lark-request-timestamp"),
        headers.get("x-lark-request-nonce"),
        raw_body,
        headers.get("x-lark-signature"),
    ):
        raise HTTPException(status_code=401, detail="invalid lark signature")

    try:
        envelope = json.loads(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="body is not valid JSON") from exc

    encrypted = envelope.get("encrypt")
    if not encrypted:
        return envelope
    if not settings.lark_encrypt_key:
        raise HTTPException(
            status_code=503,
            detail="lark sent an encrypted callback but HAALAND_LARK_ENCRYPT_KEY is not set",
        )
    try:
        return json.loads(decrypt_payload(settings.lark_encrypt_key, encrypted))
    except LarkDecryptionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="decrypted body is not valid JSON") from exc


def _assert_verification_token(settings, payload: dict) -> None:
    expected = settings.lark_verification_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="HAALAND_LARK_VERIFICATION_TOKEN is not configured",
        )
    provided = payload.get("token") or payload.get("header", {}).get("token", "")
    if not hmac.compare_digest(str(provided), expected):
        raise HTTPException(status_code=401, detail="verification token mismatch")


@router.post("/lark/card")
async def lark_card_callback(request: Request, deps=Depends(get_deps)) -> dict:
    settings = deps.settings
    if not (settings.lark_encrypt_key or settings.lark_verification_token):
        raise HTTPException(
            status_code=503,
            detail=(
                "lark callbacks are not configured; set HAALAND_LARK_ENCRYPT_KEY "
                "and/or HAALAND_LARK_VERIFICATION_TOKEN from the Lark app's "
                "Event Subscriptions page"
            ),
        )

    payload = _decoded_payload(settings, request.headers, await request.body())

    if payload.get("type") == "url_verification":
        _assert_verification_token(settings, payload)
        challenge = payload.get("challenge")
        if not challenge:
            raise HTTPException(status_code=400, detail="url_verification without a challenge")
        return {"challenge": challenge}

    raise HTTPException(
        status_code=501,
        detail=(
            "lark interactive callbacks are not implemented (docs/11 §4); "
            "approve or reject via POST /api/incidents/{reference}/approve"
        ),
    )
