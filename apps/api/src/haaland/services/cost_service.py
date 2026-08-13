from __future__ import annotations

import uuid

from haaland.llm.budget import BudgetGuard


class CostService:
    def __init__(self, guard: BudgetGuard) -> None:
        self._guard = guard

    async def record(self, incident_id: uuid.UUID, cost_usd: float) -> None:
        await self._guard.record_and_check(incident_id, cost_usd)
