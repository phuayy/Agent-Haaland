"""Lark (Feishu) notification adapters.

Two transports, one card renderer, one Protocol:

    cards.py        NotificationMessage -> Lark card JSON (shared)
    webhook_bot.py  custom-bot webhook — one chat, push-only, no setup
    app_bot.py      tenant application — org-wide, editable cards, callbacks
    client.py       Open Platform REST client behind app_bot

Which one is live is a config decision (`HAALAND_LARK_MODE`) resolved in
integrations/notify/registry.py; nothing upstream of this package knows
which transport it is talking to."""

from haaland.integrations.notify.lark.app_bot import LarkAppNotifier, infer_receive_id_type
from haaland.integrations.notify.lark.cards import build_card
from haaland.integrations.notify.lark.client import (
    BASE_URL_BY_DOMAIN,
    LarkAPIError,
    LarkAppClient,
    ReceiveIdType,
)
from haaland.integrations.notify.lark.webhook_bot import (
    LarkNotifier,
    LarkWebhookNotifier,
    lark_sign,
)

__all__ = [
    "BASE_URL_BY_DOMAIN",
    "LarkAPIError",
    "LarkAppClient",
    "LarkAppNotifier",
    "LarkNotifier",
    "LarkWebhookNotifier",
    "ReceiveIdType",
    "build_card",
    "infer_receive_id_type",
    "lark_sign",
]
