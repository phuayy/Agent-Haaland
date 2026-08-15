from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        incident_id: uuid.UUID,
        channel: str,
        target: str,
        status: str,
        external_ref: str | None,
        payload: dict,
    ) -> Notification:
        row = Notification(
            incident_id=incident_id,
            channel=channel,
            target=target,
            external_ref=external_ref,
            status=status,
            payload=payload,
        )
        self._session.add(row)
        await self._session.flush()
        return row
