from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.deployment import Deployment


class DeploymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def recent_for_service(
        self, service_id, before: datetime, lookback: timedelta = timedelta(hours=2)
    ) -> list[Deployment]:
        result = await self._session.scalars(
            select(Deployment)
            .where(
                Deployment.service_id == service_id,
                Deployment.deployed_at >= before - lookback,
                Deployment.deployed_at <= before,
            )
            .order_by(Deployment.deployed_at.desc())
        )
        return list(result)
