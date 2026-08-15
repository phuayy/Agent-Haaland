"""Operational check for the notification channels: fire a test card at
everything configured and report per-channel delivery. Lets an operator
prove the Lark webhook + signature are right before the first real
incident depends on them."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from haaland.api.deps import get_deps
from haaland.domain.models import NotificationMessage

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/channels")
async def list_channels(deps=Depends(get_deps)) -> dict:
    return {"channels": deps.notifications.channels}


@router.post("/test")
async def send_test_notification(deps=Depends(get_deps)) -> dict:
    if not deps.notifications.channels:
        return {"channels": [], "detail": "no notify channels configured (HAALAND_NOTIFY_CHANNELS)"}

    message = NotificationMessage(
        kind="test",
        title="Agent Haaland — test notification",
        body_markdown="If you can read this, the channel is wired correctly. No incident is active.",
        links={"API docs": f"{deps.settings.app_base_url}/docs"},
    )
    deliveries = await deps.notifications.broadcast(message)
    return {
        "results": [
            {"channel": d.channel, "status": d.status, "external_ref": d.external_ref, "detail": d.detail}
            for d in deliveries
        ]
    }
