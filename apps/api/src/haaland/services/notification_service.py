"""Fan-out over the configured Notifier adapters. Framework-free: depends
only on the Protocol. A channel failing is recorded and reported, never
raised — losing a Lark message must not kill an incident workflow (the
audit chain still shows exactly what was and wasn't delivered)."""

from __future__ import annotations

from dataclasses import dataclass

from haaland.domain.models import NotificationMessage
from haaland.integrations.base import NotificationError, Notifier
from haaland.logging import get_logger

logger = get_logger(__name__)


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
                logger.warning(
                    "notification channel failed",
                    channel=notifier.name,
                    kind=message.kind,
                    incident_reference=message.incident_reference,
                    detail=str(exc),
                )
                results.append(DeliveryResult(notifier.name, "failed", None, detail=str(exc)))

        # Swallowing the exception keeps the workflow alive, but a card that
        # reached nobody must still be loud somewhere: the delivery rows are
        # only visible to someone already looking at the incident, and the
        # whole point of these messages is that nobody is looking yet.
        if not self._notifiers:
            logger.debug(
                "notification dropped: no channels configured",
                kind=message.kind,
                incident_reference=message.incident_reference,
            )
        elif all(r.status == "failed" for r in results):
            logger.error(
                "notification undeliverable on every channel",
                kind=message.kind,
                incident_reference=message.incident_reference,
                channels=[r.channel for r in results],
            )
        return results
