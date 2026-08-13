"""docs/04's push/deployment_status/workflow_run/pull_request events. Out of
scope for this slice (deploy-correlation evidence isn't part of the direct
log+repo input contract) — signature verification is real; ingestion is not."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from haaland.api.deps import get_deps
from haaland.api.webhooks.signature import verify_github_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", status_code=202)
async def github_webhook(request: Request, deps=Depends(get_deps)) -> dict:
    raw_body = await request.body()
    if not verify_github_signature(
        deps.settings.github_webhook_secret, raw_body, request.headers.get("x-hub-signature-256")
    ):
        raise HTTPException(status_code=401, detail="invalid or missing signature")

    raise HTTPException(
        status_code=501,
        detail="GitHub webhook ingestion (deploy correlation) is not implemented in this slice",
    )
