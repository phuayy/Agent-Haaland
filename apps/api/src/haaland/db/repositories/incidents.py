from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.incident import Incident
from haaland.domain.enums import IncidentStatus

_TIMESTAMP_COLUMN = {
    IncidentStatus.ENRICHING: "acknowledged_at",
    IncidentStatus.TRIAGING: "triaged_at",
    IncidentStatus.DIAGNOSING: "diagnosed_at",
    IncidentStatus.APPROVED: "approved_at",
    IncidentStatus.VERIFYING: "recovered_at",
    IncidentStatus.CLOSED: "closed_at",
}


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        reference: str,
        title: str,
        repo_full_name: str | None = None,
        base_ref: str | None = None,
        status: IncidentStatus = IncidentStatus.DETECTED,
    ) -> Incident:
        row = Incident(
            reference=reference,
            title=title,
            status=status.value,
            repo_full_name=repo_full_name,
            base_ref=base_ref,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, incident_id: uuid.UUID) -> Incident | None:
        return await self._session.get(Incident, incident_id)

    async def get_by_reference(self, reference: str) -> Incident | None:
        return await self._session.scalar(select(Incident).where(Incident.reference == reference))

    async def set_status(self, incident_id: uuid.UUID, status: IncidentStatus) -> None:
        row = await self._session.get(Incident, incident_id)
        if row is None:
            raise LookupError(f"incident {incident_id} not found")
        row.status = status.value
        column = _TIMESTAMP_COLUMN.get(status)
        if column is not None and getattr(row, column) is None:
            setattr(row, column, datetime.now(UTC))
        await self._session.flush()

    async def set_severity(self, incident_id: uuid.UUID, severity: str, confidence: float) -> None:
        row = await self._session.get(Incident, incident_id)
        if row is None:
            raise LookupError(f"incident {incident_id} not found")
        row.severity = severity
        row.severity_confidence = confidence
        await self._session.flush()

    async def set_root_cause(self, incident_id: uuid.UUID, summary: str) -> None:
        row = await self._session.get(Incident, incident_id)
        if row is None:
            raise LookupError(f"incident {incident_id} not found")
        row.root_cause_summary = summary
        await self._session.flush()

    async def next_reference(self) -> str:
        from sqlalchemy import func

        year = datetime.now(UTC).year
        n = await self._session.scalar(
            select(func.count()).select_from(Incident).where(Incident.reference.like(f"INC-{year}-%"))
        )
        return f"INC-{year}-{(n or 0) + 1:04d}"
