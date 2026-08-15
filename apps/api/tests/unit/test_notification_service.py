from __future__ import annotations

from haaland.domain.models import NotificationMessage
from haaland.integrations.base import NotificationError
from haaland.services.notification_service import NotificationService


class OkNotifier:
    name = "ok"

    async def send(self, message: NotificationMessage) -> str:
        return "msg-123"


class DownNotifier:
    name = "down"

    async def send(self, message: NotificationMessage) -> str:
        raise NotificationError("webhook unreachable")


def _message() -> NotificationMessage:
    return NotificationMessage(kind="test", title="t", body_markdown="b")


async def test_one_failing_channel_does_not_stop_the_others():
    service = NotificationService([DownNotifier(), OkNotifier()])

    results = await service.broadcast(_message())

    by_channel = {r.channel: r for r in results}
    assert by_channel["down"].status == "failed"
    assert "unreachable" in by_channel["down"].detail
    assert by_channel["ok"].status == "sent"
    assert by_channel["ok"].external_ref == "msg-123"


async def test_no_channels_configured_is_a_quiet_noop():
    assert await NotificationService([]).broadcast(_message()) == []
