"""Config-driven channel selection, mirroring llm/registry.py: adding a new
channel (Slack, Teams, email, ...) is one adapter module implementing the
Notifier Protocol plus one branch here plus its settings — nothing else in
the codebase changes. HAALAND_NOTIFY_CHANNELS is a comma-separated list, so
several channels can be live at once and NotificationService fans out to
all of them."""

from __future__ import annotations

from haaland.config import Settings
from haaland.integrations.base import Notifier


def build_notifiers(settings: Settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    for channel in settings.notify_channel_list:
        if channel == "lark":
            if not settings.lark_webhook_url:
                raise RuntimeError("notify channel 'lark' requires HAALAND_LARK_WEBHOOK_URL")
            from haaland.integrations.notify.lark import LarkNotifier

            notifiers.append(
                LarkNotifier(settings.lark_webhook_url, settings.lark_webhook_secret)
            )
        else:
            raise ValueError(f"unknown notify channel: {channel!r}")
    return notifiers
