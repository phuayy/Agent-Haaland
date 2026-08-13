from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.evidence import Evidence
from haaland.domain.enums import EvidenceKind


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        incident_id: uuid.UUID,
        kind: EvidenceKind,
        source: str,
        content: dict,
        source_ref: str | None = None,
        relevance: float = 0.5,
    ) -> Evidence:
        row = Evidence(
            incident_id=incident_id,
            kind=kind.value,
            source=source,
            source_ref=source_ref,
            content=content,
            relevance=relevance,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_incident(self, incident_id: uuid.UUID) -> list[Evidence]:
        result = await self._session.scalars(
            select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.collected_at)
        )
        return list(result)
