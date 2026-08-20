"""Real provider. Every rule here is a lint-checked convention from
docs/02 / docs/05, not a style preference:

- No `temperature`, `top_p`, `top_k` — rejected by current models.
- No `budget_tokens` — use `thinking={"type": "adaptive"}` + `output_config`.
- Structured output only: `client.messages.parse()` against a Pydantic model.
- `stop_reason == "refusal"` is checked before `.content` is touched.
- The last stable system block gets the cache breakpoint; volatile content
  (incident IDs, timestamps) must never reach the system prompt — the caller
  is responsible for that split via LLMRequest.system_blocks ordering.
- Streamed when `max_tokens > 16000`.

Tool loop (explore/conclude, see llm/tools.py): exploration turns run
`messages.create` with the toolbox's tool definitions and NO output_format;
the conclusion runs `messages.parse` over the full transcript with
`tool_choice={"type": "none"}` (the tools parameter must still be present —
the API rejects histories containing tool_use blocks without it). Assistant
turns are replayed from `AssistantTurn.raw` verbatim: with adaptive thinking,
thinking blocks must survive the round-trip unmodified or the API rejects
the request.
"""

from __future__ import annotations

import time
from typing import Any

import anthropic

from haaland.llm.base import LLMRequest, LLMResult, Usage
from haaland.llm.tools import AssistantTurn, ToolCall, ToolLoopRequest, ToolSpec, ToolTurnResult

# $ per million tokens: (input, output). docs/02 section 4.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
}
_CACHE_READ_DISCOUNT = 0.1

_EFFORT_BY_STAGE = {
    "classify": "medium",
    "diagnose": "high",
    "evaluate": "high",
    "remediate": "high",
    "test": "medium",
    "report": "medium",
}


def _cost_usd(model: str, usage: Usage) -> float:
    input_price, output_price = _PRICING.get(model, (5.0, 25.0))
    cost = (
        usage.input_tokens * input_price
        + usage.output_tokens * output_price
        + usage.cache_read_tokens * input_price * _CACHE_READ_DISCOUNT
        + usage.cache_write_tokens * input_price
    ) / 1_000_000
    return round(cost, 6)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, *, default_model: str = "claude-opus-5") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    @staticmethod
    def _system_blocks(blocks: list[str]) -> list[dict]:
        rendered = []
        for i, text in enumerate(blocks):
            block: dict = {"type": "text", "text": text}
            if i == len(blocks) - 1:
                block["cache_control"] = {"type": "ephemeral"}
            rendered.append(block)
        return rendered

    @staticmethod
    def _usage(resp: Any) -> Usage:
        return Usage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        )

    def _result(self, resp: Any, model: str, start: float, *, parsed: Any) -> LLMResult:
        usage = self._usage(resp)
        return LLMResult(
            parsed=parsed,
            stop_reason=resp.stop_reason,
            usage=usage,
            cost_usd=_cost_usd(model, usage),
            latency_ms=int((time.perf_counter() - start) * 1000),
            model=model,
            provider=self.name,
            raw=resp,
        )

    async def generate(self, request: LLMRequest) -> LLMResult:
        start = time.perf_counter()
        model = request.model or self._default_model
        effort = request.effort or _EFFORT_BY_STAGE.get(request.stage, "medium")

        kwargs = dict(
            model=model,
            max_tokens=request.max_tokens,
            system=self._system_blocks(request.system_blocks),
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            output_format=request.output_schema,
            messages=[{"role": "user", "content": request.user_content.text}],
        )

        if request.max_tokens > 16000:
            async with self._client.messages.stream(**kwargs) as stream:
                resp = await stream.get_final_message()
        else:
            resp = await self._client.messages.parse(**kwargs)

        parsed = None if resp.stop_reason == "refusal" else resp.parsed_output
        return self._result(resp, model, start, parsed=parsed)

    # -- tool loop (llm/tools.py) ---------------------------------------

    @staticmethod
    def _tool_defs(tools: list[ToolSpec]) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools
        ]

    @staticmethod
    def _loop_messages(request: ToolLoopRequest) -> list[dict]:
        messages: list[dict] = [{"role": "user", "content": request.user_content.text}]
        for exchange in request.transcript:
            turn = exchange.turn
            if turn.raw is not None:
                # Replay verbatim — thinking blocks carry signatures the API
                # verifies; a reconstruction would be rejected.
                content = turn.raw
            else:
                content = [{"type": "text", "text": turn.text}] if turn.text else []
                content += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                    for c in turn.tool_calls
                ]
            messages.append({"role": "assistant", "content": content})
            if exchange.outcomes:
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": o.call_id,
                                "content": o.content.text,
                                "is_error": o.is_error,
                            }
                            for o in exchange.outcomes
                        ],
                    }
                )
        return messages

    async def explore(self, request: ToolLoopRequest) -> ToolTurnResult:
        start = time.perf_counter()
        model = request.model or self._default_model

        resp = await self._client.messages.create(
            model=model,
            max_tokens=request.max_tokens,
            system=self._system_blocks(request.system_blocks),
            thinking={"type": "adaptive"},
            output_config={"effort": request.effort},
            tools=self._tool_defs(request.tools),
            messages=self._loop_messages(request),
        )

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))

        turn = AssistantTurn(text="\n".join(text_parts), tool_calls=tuple(calls), raw=resp.content)
        return ToolTurnResult(turn=turn, result=self._result(resp, model, start, parsed=None))

    async def conclude(self, request: ToolLoopRequest) -> LLMResult:
        start = time.perf_counter()
        model = request.model or self._default_model

        resp = await self._client.messages.parse(
            model=model,
            max_tokens=request.max_tokens,
            system=self._system_blocks(request.system_blocks),
            thinking={"type": "adaptive"},
            output_config={"effort": request.effort},
            tools=self._tool_defs(request.tools),
            tool_choice={"type": "none"},
            output_format=request.output_schema,
            messages=self._loop_messages(request),
        )
        parsed = None if resp.stop_reason == "refusal" else resp.parsed_output
        return self._result(resp, model, start, parsed=parsed)
