"""Operational checks for the notification channels: prove the wiring works
before the first real incident depends on it.

The three Lark failure modes an operator actually hits — wrong
app_id/secret, right credentials but the bot is not in the chat, right chat
but the wrong id — are indistinguishable from a single "send failed". So
they get separate endpoints: `/lark/verify` isolates credentials,
`/lark/chats` isolates membership and hands back the chat_id to configure,
and `/test` proves end-to-end delivery. Read-only diagnostics, no secrets in
any response."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from haaland.api.deps import get_deps
from haaland.domain.models import NotificationMessage
from haaland.integrations.notify.lark import LarkAPIError, LarkAppClient

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _lark_client(deps) -> LarkAppClient:
    """The Lark app client, or a 409 explaining exactly which switch is
    off — these routes are meaningless against a custom webhook bot, which
    has no organisation-level API."""
    if deps.lark is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "the Lark tenant application is not configured: needs "
                "HAALAND_NOTIFY_CHANNELS to include 'lark', HAALAND_LARK_MODE=app, "
                "and HAALAND_LARK_APP_ID/HAALAND_LARK_APP_SECRET"
            ),
        )
    return deps.lark


@router.get("/channels")
async def list_channels(deps=Depends(get_deps)) -> dict:
    return {
        "channels": deps.notifications.channels,
        "lark_mode": deps.settings.lark_mode,
        "lark_domain": deps.settings.lark_domain,
    }


@router.get("/lark/verify")
async def verify_lark_credentials(deps=Depends(get_deps)) -> dict:
    """Exchanges a fresh tenant_access_token. Success proves app_id,
    app_secret and domain agree with the Lark side; it proves nothing about
    scopes or chat membership."""
    client = _lark_client(deps)
    try:
        return await client.verify_credentials()
    except LarkAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/lark/chats")
async def list_lark_chats(deps=Depends(get_deps)) -> dict:
    """The chats the bot is a member of — copy the `chat_id` of the target
    group into HAALAND_LARK_DEFAULT_RECEIVE_ID. An empty list means the bot
    has not been added to any chat yet (add it in the chat's Settings ->
    Bots), not that the credentials are wrong."""
    client = _lark_client(deps)
    try:
        chats = await client.list_chats()
    except LarkAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"chats": chats, "count": len(chats)}


@router.post("/test")
async def send_test_notification(
    deps=Depends(get_deps),
    target: str | None = Query(
        default=None,
        description=(
            "Override the channel's default destination for this one message — "
            "a Lark chat_id (oc_…), open_id (ou_…) or work email. Ignored by "
            "transports bound to a fixed destination, such as a custom webhook bot."
        ),
    ),
) -> dict:
    if not deps.notifications.channels:
        return {"channels": [], "detail": "no notify channels configured (HAALAND_NOTIFY_CHANNELS)"}

    message = NotificationMessage(
        kind="test",
        title="Agent Haaland — test notification",
        body_markdown="If you can read this, the channel is wired correctly. No incident is active.",
        links={"API docs": f"{deps.settings.app_base_url}/docs"},
        target=target,
    )
    deliveries = await deps.notifications.broadcast(message)
    return {
        "results": [
            {
                "channel": d.channel,
                "status": d.status,
                "external_ref": d.external_ref,
                "detail": d.detail,
            }
            for d in deliveries
        ]
    }
