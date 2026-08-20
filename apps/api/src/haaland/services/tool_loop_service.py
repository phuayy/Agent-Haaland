"""The agentic exploration loop: let the model grep and read the workspace
itself, Claude Code style, instead of only choosing among pre-located
candidates. One call site mirroring LLMCallService — invoke, persist every
turn to ai_analyses, enforce budget per turn, redact tool output, force a
structured conclusion — so agentic and single-shot stages account for cost
and auditability identically.

Guarantees the loop enforces (the model gets no say in any of them):

- at most `max_iterations` exploration turns, then a forced conclusion;
- every tool result passes through Redactor.redact_text before the model
  sees it — the redaction choke point (docs/05) covers tool output too;
- BudgetGuard.record_and_check runs after every turn, so a runaway loop
  halts on the same BudgetExceeded path as any other overspend;
- tools are the read-only CodeToolbox; a failed call becomes an is_error
  result, never an exception out of the loop.

Framework-free: depends on the ToolCallingLLMProvider Protocol,
repositories and the Redactor — never on langgraph or a vendor SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final, Literal, TypeVar, cast

from pydantic import BaseModel

from haaland.db.repositories.ai_analyses import AIAnalysisRepository
from haaland.domain.errors import AIRefusalError
from haaland.llm.base import RedactedPayload
from haaland.llm.budget import BudgetGuard
from haaland.llm.prompts import load_prompt, load_stage_instructions, load_system_base
from haaland.llm.tools import (
    ToolCallingLLMProvider,
    ToolExchange,
    ToolLoopRequest,
    ToolOutcome,
    ToolTurnResult,
)
from haaland.redaction.service import Redactor
from haaland.services.code_toolbox import CodeToolbox

T = TypeVar("T", bound=BaseModel)

# Exploration turns emit a short thought plus tool calls; the conclusion is
# the stage's real deliverable and gets the diagnose-sized ceiling.
_EXPLORE_MAX_TOKENS = 4000
_CONCLUDE_MAX_TOKENS = 16000
_EXPLORE_EFFORT: Final[Literal["medium"]] = "medium"
_CONCLUDE_EFFORT: Final[Literal["high"]] = "high"


@dataclass
class ToolLoopOutcome[ParsedT: BaseModel]:
    parsed: ParsedT
    turns: int  # model turns consumed, conclusion included
    tool_calls: int  # tool calls executed


class ToolLoopService:
    def __init__(
        self,
        llm: ToolCallingLLMProvider,
        analyses: AIAnalysisRepository,
        budget: BudgetGuard,
        redactor: Redactor,
        *,
        max_iterations: int = 12,
    ) -> None:
        self._llm = llm
        self._analyses = analyses
        self._budget = budget
        self._redactor = redactor
        self._max_iterations = max_iterations

    async def run(
        self,
        *,
        incident_id: uuid.UUID,
        stage: str,
        redacted_text: str,
        output_schema: type[T],
        toolbox: CodeToolbox,
        redaction_map_id: uuid.UUID | None = None,
    ) -> ToolLoopOutcome[T]:
        base = load_system_base()
        stage_prompt = load_stage_instructions(stage)
        loop_prompt = load_prompt("system/tool_loop.md")
        system_blocks = [base.text, stage_prompt.text, loop_prompt.text]
        tools = toolbox.specs()

        transcript: list[ToolExchange] = []
        total_tool_calls = 0
        model_turns = 0

        for turn_no in range(self._max_iterations):
            turn = await self._llm.explore(
                ToolLoopRequest(
                    stage=stage,
                    system_blocks=system_blocks,
                    user_content=RedactedPayload(redacted_text),
                    output_schema=output_schema,
                    tools=tools,
                    transcript=transcript,
                    effort=_EXPLORE_EFFORT,
                    max_tokens=_EXPLORE_MAX_TOKENS,
                )
            )
            model_turns += 1
            await self._record(incident_id, stage, turn, turn_no, redaction_map_id)
            await self._budget.record_and_check(incident_id, turn.result.cost_usd)
            if turn.result.refused:
                raise AIRefusalError(stage)
            if not turn.turn.tool_calls:
                # The model is done exploring; keep its closing reasoning
                # visible to the conclusion turn.
                transcript.append(ToolExchange(turn=turn.turn))
                break

            outcomes: list[ToolOutcome] = []
            for call in turn.turn.tool_calls:
                content, is_error = toolbox.execute(call)
                redacted = await self._redactor.redact_text(incident_id, content)
                outcomes.append(
                    ToolOutcome(call_id=call.id, name=call.name, content=redacted, is_error=is_error)
                )
            total_tool_calls += len(outcomes)
            transcript.append(ToolExchange(turn=turn.turn, outcomes=tuple(outcomes)))

        result = await self._llm.conclude(
            ToolLoopRequest(
                stage=stage,
                system_blocks=system_blocks,
                user_content=RedactedPayload(redacted_text),
                output_schema=output_schema,
                tools=tools,
                transcript=transcript,
                effort=_CONCLUDE_EFFORT,
                max_tokens=_CONCLUDE_MAX_TOKENS,
            )
        )
        model_turns += 1
        await self._analyses.record(
            incident_id=incident_id,
            stage=stage,
            prompt=stage_prompt,
            result=result,
            request_payload={
                "phase": "conclude",
                "explore_turns": model_turns - 1,
                "tool_calls": total_tool_calls,
            },
            redaction_map_id=redaction_map_id,
        )
        await self._budget.record_and_check(incident_id, result.cost_usd)

        if result.refused or result.parsed is None:
            raise AIRefusalError(stage)
        return ToolLoopOutcome(
            parsed=cast(T, result.parsed), turns=model_turns, tool_calls=total_tool_calls
        )

    async def _record(
        self,
        incident_id: uuid.UUID,
        stage: str,
        turn: ToolTurnResult,
        turn_no: int,
        redaction_map_id: uuid.UUID | None,
    ) -> None:
        await self._analyses.record(
            incident_id=incident_id,
            stage=stage,
            prompt=load_stage_instructions(stage),
            result=turn.result,
            request_payload={
                "phase": "explore",
                "turn": turn_no,
                "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in turn.turn.tool_calls],
            },
            redaction_map_id=redaction_map_id,
        )
