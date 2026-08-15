"""Fan-out over the configured Notifier adapters. Framework-free: depends
only on the Protocol. A channel failing is recorded and reported, never
raised — losing a Lark message must not kill an incident workflow (the
audit chain still shows exactly what was and wasn't delivered)."""

from __future__ import annotations

from dataclasses import dataclass

from haaland.domain.models import NotificationMessage
from haaland.integrations.base import NotificationError, Notifier


@dataclass(frozen=True)
class DeliveryResult:
    channel: str
    status: str  # 'sent' | 'failed'
    external_ref: str | None
    detail: str | None = None


class NotificationService:
    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = notifiers

    @property
    def channels(self) -> list[str]:
        return [n.name for n in self._notifiers]

    async def broadcast(self, message: NotificationMessage) -> list[DeliveryResult]:
        results: list[DeliveryResult] = []
        for notifier in self._notifiers:
            try:
                ref = await notifier.send(message)
                results.append(DeliveryResult(notifier.name, "sent", ref))
            except NotificationError as exc:
                results.append(DeliveryResult(notifier.name, "failed", None, detail=str(exc)))
        return results
