"""Per-incident and daily USD ceilings. Exceeding either halts the pipeline
and pages a human with whatever was produced (docs/05, docs/09) — it never
fails silently and it never blocks detection."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from haaland.domain.errors import BudgetExceeded


class BudgetGuard:
    def __init__(self, redis: Redis, *, per_incident_usd: float, per_day_usd: float) -> None:
        self._redis = redis
        self._per_incident = per_incident_usd
        self._per_day = per_day_usd

    def _incident_key(self, incident_id: uuid.UUID) -> str:
        return f"cost:incident:{incident_id}"

    def _day_key(self) -> str:
        return f"cost:day:{datetime.now(UTC):%Y-%m-%d}"

    async def record_and_check(self, incident_id: uuid.UUID, cost_usd: float) -> None:
        incident_total = await self._redis.incrbyfloat(self._incident_key(incident_id), cost_usd)
        await self._redis.expire(self._incident_key(incident_id), 7 * 24 * 3600)
        day_total = await self._redis.incrbyfloat(self._day_key(), cost_usd)
        await self._redis.expire(self._day_key(), 2 * 24 * 3600)

        if float(incident_total) > self._per_incident:
            raise BudgetExceeded(float(incident_total), self._per_incident, scope=f"incident:{incident_id}")
        if float(day_total) > self._per_day:
            raise BudgetExceeded(float(day_total), self._per_day, scope="daily")
