"""Config-driven channel selection, mirroring llm/registry.py: adding a new
channel (Slack, Teams, email, ...) is one adapter module implementing the
Notifier Protocol plus one branch here plus its settings — nothing else in
the codebase changes. HAALAND_NOTIFY_CHANNELS is a comma-separated list, so
several channels can be live at once and NotificationService fans out to
all of them.

Lark is one channel with two transports (`HAALAND_LARK_MODE`), not two
channels: upstream code, the audit rows and the operator endpoints should
all keep saying "lark" whether delivery happens over a custom webhook bot or
the tenant application. Every misconfiguration below raises at startup, not
at the first incident — the same fail-fast posture as config.py."""

from __future__ import annotations

from haaland.config import Settings
from haaland.integrations.base import Notifier
from haaland.integrations.notify.lark import LarkAppClient, LarkAppNotifier, LarkWebhookNotifier


def build_lark_client(settings: Settings) -> LarkAppClient | None:
    """The Lark Open Platform client, or None unless the Lark channel is
    enabled *and* running the app transport. Shared by the notifier and by
    the operator-facing diagnostics routes (api/routes/notifications.py), so
    credentials and the token cache exist once per process."""
    if settings.lark_mode != "app" or "lark" not in settings.notify_channel_list:
        return None
    if not (settings.lark_app_id and settings.lark_app_secret):
        raise RuntimeError(
            "HAALAND_LARK_MODE=app requires HAALAND_LARK_APP_ID and HAALAND_LARK_APP_SECRET"
        )
    return LarkAppClient(
        settings.lark_app_id, settings.lark_app_secret, domain=settings.lark_domain
    )


def _build_lark_notifier(settings: Settings, client: LarkAppClient | None) -> Notifier:
    if settings.lark_mode == "app":
        if client is None:
            raise RuntimeError("HAALAND_LARK_MODE=app but no Lark client was built")
        if not settings.lark_default_receive_id:
            raise RuntimeError(
                "HAALAND_LARK_MODE=app requires HAALAND_LARK_DEFAULT_RECEIVE_ID "
                "(a chat_id like oc_…, an open_id like ou_…, or a work email). "
                "GET /api/notifications/lark/chats lists the chats the bot is in."
            )
        return LarkAppNotifier(
            client,
            settings.lark_default_receive_id,
            default_receive_id_type=settings.lark_default_receive_id_type,
        )

    if not settings.lark_webhook_url:
        raise RuntimeError(
            "notify channel 'lark' in webhook mode requires HAALAND_LARK_WEBHOOK_URL "
            "(or set HAALAND_LARK_MODE=app)"
        )
    return LarkWebhookNotifier(settings.lark_webhook_url, settings.lark_webhook_secret)


def build_notifiers(settings: Settings, lark_client: LarkAppClient | None = None) -> list[Notifier]:
    notifiers: list[Notifier] = []
    for channel in settings.notify_channel_list:
        if channel == "lark":
            notifiers.append(_build_lark_notifier(settings, lark_client))
        else:
            raise ValueError(f"unknown notify channel: {channel!r}")
    return notifiers
