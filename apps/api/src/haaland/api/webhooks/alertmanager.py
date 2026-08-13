"""The alert-triggered detection path from docs/01 Stage 1. Out of scope for
this slice per the plan (needs the LGTM observability plane, docs Phase 0/1)
— verification is real and wired so the endpoint is honest about auth, but
ingestion returns 501 rather than silently doing nothing. Use
POST /api/debug-sessions for the direct-input path this slice implements."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from haaland.api.deps import get_deps
from haaland.api.webhooks.signature import verify_bearer

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/alertmanager", status_code=202)
async def alertmanager_webhook(request: Request, deps=Depends(get_deps)) -> dict:
    if not verify_bearer(deps.settings.alertmanager_webhook_token, request.headers.get("authorization")):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    raise HTTPException(
        status_code=501,
        detail="alert-triggered ingestion is not implemented in this slice; "
        "submit via POST /api/debug-sessions instead",
    )
