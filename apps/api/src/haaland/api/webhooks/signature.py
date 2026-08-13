"""All HMAC/bearer verification lives here — one module, per docs/09,
so there is exactly one place to audit for the "verify before parsing"
webhook rule. Every function takes the raw body; never verify against a
re-serialised JSON object."""

from __future__ import annotations

import hmac
import time
from hashlib import sha256


def verify_bearer(expected_token: str | None, authorization_header: str | None) -> bool:
    if not expected_token:
        return False
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return False
    provided = authorization_header.removeprefix("Bearer ")
    return hmac.compare_digest(provided, expected_token)


def verify_github_signature(secret: str | None, raw_body: bytes, signature_header: str | None) -> bool:
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def verify_slack_signature(
    signing_secret: str | None, timestamp: str | None, raw_body: bytes, signature_header: str | None,
    *, replay_window_seconds: int = 300,
) -> bool:
    if not signing_secret or not timestamp or not signature_header:
        return False
    try:
        if abs(time.time() - int(timestamp)) > replay_window_seconds:
            return False
    except ValueError:
        return False
    basestring = f"v0:{timestamp}:{raw_body.decode()}"
    expected = "v0=" + hmac.new(signing_secret.encode(), basestring.encode(), sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
