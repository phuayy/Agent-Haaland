"""One call site for "invoke the model, persist the audit row, enforce
budget, handle refusal" — used by every stage node (classify, diagnose,
evaluate, remediate, test, report) so that behaviour is identical across
all six instead of re-implemented per node. Framework-free: depends on the
LLMProvider Protocol and repositories, never on langgraph or fastapi."""

from __future__ import annotations

import uuid
from typing import TypeVar

from pydantic import BaseModel

from haaland.db.repositories.ai_analyses import AIAnalysisRepository
from haaland.domain.errors import AIRefusalError
from haaland.llm.base import LLMProvider, LLMRequest, RedactedPayload
from haaland.llm.budget import BudgetGuard
from haaland.llm.prompts import load_stage_instructions, load_system_base

T = TypeVar("T", bound=BaseModel)

_EFFORT_BY_STAGE = {
    "classify": "medium",
    "diagnose": "high",
    "evaluate": "high",
    "remediate": "high",
    "test": "medium",
    "report": "medium",
}
_MAX_TOKENS_BY_STAGE = {
    "classify": 4000,
    "diagnose": 16000,
    "evaluate": 8000,
    "remediate": 12000,
    "test": 6000,
    "report": 20000,
}


class LLMCallService:
    def __init__(self, llm: LLMProvider, analyses: AIAnalysisRepository, budget: BudgetGuard) -> None:
        self._llm = llm
        self._analyses = analyses
        self._budget = budget

    async def call(
        self,
        *,
        incident_id: uuid.UUID,
        stage: str,
        redacted_text: str,
        output_schema: type[T],
        redaction_map_id: uuid.UUID | None = None,
        extra_system_block: str | None = None,
    ) -> T:
        base = load_system_base()
        stage_prompt = load_stage_instructions(stage)
        system_blocks = [base.text, stage_prompt.text]
        if extra_system_block:
            system_blocks.append(extra_system_block)

        request = LLMRequest(
            stage=stage,
            system_blocks=system_blocks,
            user_content=RedactedPayload(redacted_text),
            output_schema=output_schema,
            effort=_EFFORT_BY_STAGE.get(stage, "medium"),
            max_tokens=_MAX_TOKENS_BY_STAGE.get(stage, 8000),
        )
        result = await self._llm.generate(request)

        await self._analyses.record(
            incident_id=incident_id,
            stage=stage,
            prompt=stage_prompt,
            result=result,
            request_payload={"stage": stage, "system_block_count": len(system_blocks)},
            redaction_map_id=redaction_map_id,
        )
        await self._budget.record_and_check(incident_id, result.cost_usd)

        if result.refused or result.parsed is None:
            raise AIRefusalError(stage)

        return result.parsed
