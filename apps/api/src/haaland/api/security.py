"""First-party API authentication. One bearer token guards every /api/*
route — the debug-session entrypoint (triggers clones and LLM spend), the
approval gate (the product's safety claim), and the operator diagnostics.
Webhooks are exempt on purpose: each one verifies its own upstream
signature in api/webhooks/ instead.

Unset token = open access, kept as a dev/compose convenience only;
config.py refuses to start in prod without a token, so this dependency can
never silently no-op on a public deployment."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from haaland.api.deps import get_deps
from haaland.api.webhooks.signature import verify_bearer


async def require_api_auth(request: Request, deps=Depends(get_deps)) -> None:
    expected = deps.settings.api_auth_token
    if expected is None:
        return
    if not verify_bearer(expected, request.headers.get("authorization")):
        raise HTTPException(
            status_code=401,
            detail="invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
