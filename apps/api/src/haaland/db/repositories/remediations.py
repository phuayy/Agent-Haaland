from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.remediation import Remediation


class RemediationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        incident_id: uuid.UUID,
        strategy: str,
        rationale: str,
        risk_notes: str | None,
        repo_full_name: str,
        branch_name: str,
        base_sha: str,
        patch: str,
        attempt_count: int,
    ) -> Remediation:
        row = Remediation(
            incident_id=incident_id,
            strategy=strategy,
            rationale=rationale,
            risk_notes=risk_notes,
            repo_full_name=repo_full_name,
            branch_name=branch_name,
            base_sha=base_sha,
            patch=patch,
            attempt_count=attempt_count,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def set_pr(self, remediation_id: uuid.UUID, *, pr_number: int, pr_url: str) -> None:
        row = await self._session.get(Remediation, remediation_id)
        if row is None:
            return
        row.pr_number = pr_number
        row.pr_url = pr_url
        row.status = "pending"
        await self._session.flush()

    async def resolve(self, remediation_id: uuid.UUID, status: str) -> None:
        row = await self._session.get(Remediation, remediation_id)
        if row is None:
            return
        row.status = status
        row.resolved_at = datetime.now(UTC)
        await self._session.flush()

    async def list_for_incident(self, incident_id: uuid.UUID) -> list[Remediation]:
        result = await self._session.scalars(
            select(Remediation)
            .where(Remediation.incident_id == incident_id)
            .order_by(Remediation.created_at.asc())
        )
        return list(result)
