"""Lark **tenant application** transport — the org-connected bot.

Same Notifier Protocol, same card, different reach: this adapter posts
through the Lark Open Platform as an installed application, so one
configured bot can address any chat it belongs to and any person in the
organisation, rather than being nailed to a single webhook URL.

Routing rule: `NotificationMessage.target` wins when set, otherwise the
configured default chat. The id *type* is inferred from Lark's id prefixes
(`oc_` chat, `ou_` user, `on_` union) with an "@" meaning an email address,
falling back to the configured default type. That inference is here rather
than in the client so the client stays a plain API wrapper, and so callers
upstream can keep passing one opaque string without knowing Lark's
taxonomy."""

from __future__ import annotations

from haaland.domain.models import NotificationMessage
from haaland.integrations.notify.lark.cards import build_card
from haaland.integrations.notify.lark.client import LarkAppClient, ReceiveIdType

_ID_PREFIXES: tuple[tuple[str, ReceiveIdType], ...] = (
    ("oc_", "chat_id"),
    ("ou_", "open_id"),
    ("on_", "union_id"),
)


def infer_receive_id_type(receive_id: str, default: ReceiveIdType) -> ReceiveIdType:
    for prefix, id_type in _ID_PREFIXES:
        if receive_id.startswith(prefix):
            return id_type
    if "@" in receive_id:
        return "email"
    return default


class LarkAppNotifier:
    """Implements the Notifier Protocol (integrations/base.py)."""

    name = "lark"

    def __init__(
        self,
        client: LarkAppClient,
        default_receive_id: str,
        *,
        default_receive_id_type: ReceiveIdType = "chat_id",
    ) -> None:
        self._client = client
        self._default_receive_id = default_receive_id
        self._default_receive_id_type = default_receive_id_type

    async def send(self, message: NotificationMessage) -> str:
        receive_id = message.target or self._default_receive_id
        receive_id_type = infer_receive_id_type(receive_id, self._default_receive_id_type)
        return await self._client.send_card(
            receive_id, build_card(message), receive_id_type=receive_id_type
        )
