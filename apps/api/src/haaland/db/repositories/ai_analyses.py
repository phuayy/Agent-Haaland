from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.ai_analysis import AIAnalysis
from haaland.llm.base import LLMResult
from haaland.llm.prompts import Prompt


class AIAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        incident_id: uuid.UUID,
        stage: str,
        prompt: Prompt,
        result: LLMResult,
        request_payload: dict,
        redaction_map_id: uuid.UUID | None,
    ) -> AIAnalysis:
        row = AIAnalysis(
            incident_id=incident_id,
            stage=stage,
            provider=result.provider,
            model=result.model,
            prompt_version=prompt.qualified_version,
            prompt_hash=prompt.sha256,
            redaction_map_id=redaction_map_id,
            request_payload=request_payload,
            response_payload=result.parsed.model_dump(mode="json") if result.parsed else {},
            stop_reason=result.stop_reason,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_read_tokens=result.usage.cache_read_tokens,
            cache_write_tokens=result.usage.cache_write_tokens,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row
