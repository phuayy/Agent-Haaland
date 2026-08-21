"""Provider-neutral tool-calling contract — the type boundary for the
agentic read/grep loop (Claude Code's explore pattern applied to diagnosis).

The loop is two-phase by design:

- *explore* turns are free-form: the model returns text plus zero or more
  tool calls, the caller executes them and appends the results, repeat;
- the *conclude* turn disables tools and reuses each provider's existing
  structured-output path over the full exploration transcript.

Two phases rather than one because DeepSeek cannot combine JSON mode
(`response_format={"type": "json_object"}`) with function calls — a
single-phase design would work on exactly one provider. Two phases keep
the transcript provider-neutral and leave every provider's validated
structured-output path untouched.

`ToolOutcome.content` is a `RedactedPayload` for the same reason
`LLMRequest.user_content` is: tool output is workspace content and must
pass through the Redactor before the model sees it. There is no overload
that accepts a raw string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from haaland.llm.base import LLMResult, RedactedPayload


@dataclass(frozen=True)
class ToolSpec:
    """One callable tool, described provider-neutrally. `input_schema` is a
    JSON Schema object; each provider wraps it in its own envelope."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolOutcome:
    """The executed result of one ToolCall, already redacted."""

    call_id: str
    name: str
    content: RedactedPayload
    is_error: bool = False


@dataclass(frozen=True)
class AssistantTurn:
    """One assistant exploration turn. `raw` is an opaque replay payload
    (Anthropic content blocks including thinking blocks, or the OpenAI-shaped
    assistant message dict). Only the provider that produced it reads it —
    Anthropic requires thinking blocks to be replayed verbatim across tool
    turns, and a neutral text+calls reconstruction would drop them."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    raw: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class ToolExchange:
    """One explore turn plus the executed results of its tool calls."""

    turn: AssistantTurn
    outcomes: tuple[ToolOutcome, ...] = ()


@dataclass
class ToolLoopRequest:
    stage: str
    system_blocks: list[str]
    user_content: RedactedPayload
    output_schema: type[BaseModel]
    tools: list[ToolSpec]
    transcript: list[ToolExchange] = field(default_factory=list)
    effort: Literal["low", "medium", "high"] = "medium"
    max_tokens: int = 8000
    model: str | None = None
    # Ephemeral per-turn status line ("turns remaining: N", convergence
    # nudges) rendered by each provider as a trailing user-side message.
    # Set by the loop on explore turns only; never part of the transcript.
    turn_note: str | None = None


@dataclass
class ToolTurnResult:
    """One explore turn's outcome. `result.parsed` is always None here —
    structured output only exists on the conclude turn — but usage, cost and
    stop_reason are real, so the turn can be recorded on ai_analyses and
    charged against BudgetGuard exactly like a single-shot call."""

    turn: AssistantTurn
    result: LLMResult


@runtime_checkable
class ToolCallingLLMProvider(Protocol):
    """Optional capability on top of LLMProvider. Providers that don't
    implement it (fake, openai) still work — callers must check
    `supports_tool_loop` and fall back to single-shot `generate`."""

    name: str

    async def explore(self, request: ToolLoopRequest) -> ToolTurnResult: ...

    async def conclude(self, request: ToolLoopRequest) -> LLMResult: ...


def supports_tool_loop(provider: object) -> bool:
    return isinstance(provider, ToolCallingLLMProvider)
