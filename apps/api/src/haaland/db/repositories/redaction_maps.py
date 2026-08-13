from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.redaction_map import RedactionMap


class RedactionMapRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self, *, incident_id: uuid.UUID, vault_key: str, entity_counts: dict, ttl_hours: int
    ) -> RedactionMap:
        row = RedactionMap(
            incident_id=incident_id,
            vault_key=vault_key,
            entity_counts=entity_counts,
            recogniser_versions={"regex_prefilter": "1"},
            expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
        )
        self._session.add(row)
        await self._session.flush()
        return row
