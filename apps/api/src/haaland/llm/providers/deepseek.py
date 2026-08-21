"""DeepSeek provider — the default real provider.

DeepSeek exposes two compatible surfaces (https://api-docs.deepseek.com): an
OpenAI-compatible one at `https://api.deepseek.com` and an Anthropic-compatible
one at `https://api.deepseek.com/anthropic`. This module uses the
OpenAI-compatible surface via the `openai` SDK, for one decisive reason: the
Anthropic-compatible endpoint ignores `cache_control` and does not implement
Anthropic's structured-output path (`output_format` / `messages.parse`), and
every stage of this pipeline depends on a validated Pydantic object coming
back. Routing through the Anthropic envelope would silently lose that.

The one real difference from `providers/openai.py`: DeepSeek supports
`response_format={"type": "json_object"}` (JSON mode) but NOT strict
`json_schema` structured output, so `chat.completions.parse()` cannot be used.
Instead the JSON Schema of the requested model is appended as a final system
block and the response is validated with Pydantic here, with one repair retry
when the model returns JSON that does not fit the schema.

Other DeepSeek-specific rules encoded here:
- Thinking is opt-in per request: `extra_body={"thinking": {"type": "enabled"}}`.
- `reasoning_effort` accepts "low" | "high" | "max" — not "medium"; the
  provider-neutral effort levels on LLMRequest are mapped in _EFFORT_MAP.
- Usage splits input into `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`.
  Miss maps to Usage.input_tokens and hit to Usage.cache_read_tokens, so the
  numbers on `ai_analyses` mean the same thing as on the Anthropic path
  (input_tokens = uncached input). DeepSeek's context cache is implicit, so
  there is no cache-write charge and cache_write_tokens is always 0.
- Pricing is time-of-day dependent (peak vs off-peak UTC). _cost_usd applies
  the published rate for the current window; it is an estimate for BudgetGuard,
  not a billing record.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from haaland.llm.base import LLMRequest, LLMResult, Usage
from haaland.llm.tools import AssistantTurn, ToolCall, ToolLoopRequest, ToolSpec, ToolTurnResult

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# $ per million tokens: (cache-hit input, cache-miss input, output). Off-peak and
# peak rates per api-docs.deepseek.com/quick_start/pricing.
_PRICING_OFF_PEAK: dict[str, tuple[float, float, float]] = {
    "deepseek-v4-flash": (0.007, 0.22, 0.66),
    "deepseek-v4-pro": (0.022, 0.66, 1.98),
}
_PRICING_PEAK: dict[str, tuple[float, float, float]] = {
    "deepseek-v4-flash": (0.014, 0.44, 1.32),
    "deepseek-v4-pro": (0.044, 1.32, 3.96),
}
# Peak windows are 01:00-04:00 and 06:00-10:00 UTC; everything else is off-peak.
_PEAK_HOURS_UTC = frozenset(range(1, 4)) | frozenset(range(6, 10))

# LLMRequest.effort is provider-neutral ("low" | "medium" | "high"); DeepSeek's
# reasoning_effort scale is "low" | "high" | "max" and defaults to "high".
_EFFORT_MAP = {"low": "low", "medium": "high", "high": "max"}

# Stream at or above this ceiling — long completions over plain HTTP risk
# idle-timeout resets, and reasoning tokens inflate wall time well before the
# first output byte.
_STREAM_ABOVE_MAX_TOKENS = 8000
# On finish_reason="length" the retry raises the ceiling (doubling, capped
# here) instead of repeating the same truncation with the same budget.
_MAX_RETRY_MAX_TOKENS = 65536

_SCHEMA_BLOCK = (
    "## Output format\n"
    "Reply with a single json object and nothing else - no prose, no markdown "
    "fences, no trailing commentary. The json object must validate against this "
    "JSON Schema exactly; include every required property and use the exact "
    "property names given:\n\n```json\n{schema}\n```"
)


def _is_peak(now: datetime | None = None) -> bool:
    return (now or datetime.now(UTC)).astimezone(UTC).hour in _PEAK_HOURS_UTC


def _cost_usd(model: str, usage: Usage, *, peak: bool | None = None) -> float:
    table = _PRICING_PEAK if (_is_peak() if peak is None else peak) else _PRICING_OFF_PEAK
    hit_price, miss_price, output_price = table.get(model, table["deepseek-v4-pro"])
    cost = (
        usage.cache_read_tokens * hit_price
        + usage.input_tokens * miss_price
        + usage.output_tokens * output_price
    ) / 1_000_000
    return round(cost, 6)


def schema_block(output_schema: type[BaseModel]) -> str:
    """The extra system block that stands in for strict structured output."""
    schema = json.dumps(output_schema.model_json_schema(), indent=2, sort_keys=True)
    return _SCHEMA_BLOCK.format(schema=schema)


def extract_json(text: str) -> str:
    """Tolerate a model that wraps its json in a fence or adds a preamble."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -len("```")]
        body = body.strip()
    start, end = body.find("{"), body.rfind("}")
    if start != -1 and end > start:
        return body[start : end + 1]
    return body


def parse_payload(text: str, output_schema: type[BaseModel]) -> BaseModel:
    """Raises ValidationError / ValueError for the repair path to catch."""
    return output_schema.model_validate_json(extract_json(text))


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "deepseek-v4-flash",
        base_url: str = DEEPSEEK_BASE_URL,
        thinking: bool = True,
        repair_attempts: int = 1,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._default_model = default_model
        self._thinking = thinking
        self._repair_attempts = repair_attempts

    def _messages(self, request: LLMRequest) -> list[dict[str, str]]:
        system = "\n\n".join([*request.system_blocks, schema_block(request.output_schema)])
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": request.user_content.text},
        ]

    async def _complete(
        self,
        model: str,
        request: LLMRequest | ToolLoopRequest,
        messages: list[dict[str, Any]],
        extra_kwargs: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, str, Any, Any]:
        effective_max_tokens = max_tokens or request.max_tokens
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=messages,
            max_tokens=effective_max_tokens,
            response_format={"type": "json_object"},
            reasoning_effort=_EFFORT_MAP.get(request.effort, "high"),
            **(extra_kwargs or {}),
        )
        if self._thinking:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        if effective_max_tokens >= _STREAM_ABOVE_MAX_TOKENS:
            return await self._complete_streaming(kwargs)

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        return choice.message.content or "", (choice.finish_reason or "stop"), resp.usage, resp

    async def _complete_streaming(self, kwargs: dict[str, Any]) -> tuple[str, str, Any, Any]:
        """Long report/diagnose outputs stream, mirroring the Anthropic path."""
        chunks: list[str] = []
        finish_reason = "stop"
        usage = None
        stream = await self._client.chat.completions.create(
            **kwargs, stream=True, stream_options={"include_usage": True}
        )
        async for event in stream:
            if getattr(event, "usage", None) is not None:
                usage = event.usage
            for choice in event.choices:
                if choice.delta and choice.delta.content:
                    chunks.append(choice.delta.content)
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        return "".join(chunks), finish_reason, usage, None

    def _usage(self, raw_usage: Any) -> Usage:
        if raw_usage is None:
            return Usage()
        prompt_tokens = getattr(raw_usage, "prompt_tokens", 0) or 0
        cache_hit = getattr(raw_usage, "prompt_cache_hit_tokens", 0) or 0
        cache_miss = getattr(raw_usage, "prompt_cache_miss_tokens", None)
        # If the cache fields are absent, treat the whole prompt as a miss so the
        # budget guard over-estimates rather than under-estimates.
        if cache_miss is None:
            cache_miss = prompt_tokens - cache_hit
        return Usage(
            input_tokens=max(cache_miss, 0),
            output_tokens=getattr(raw_usage, "completion_tokens", 0) or 0,
            cache_read_tokens=cache_hit,
            cache_write_tokens=0,  # implicit cache: nothing is charged to write it
        )

    @staticmethod
    def _accumulate(total: Usage, attempt: Usage) -> Usage:
        return Usage(
            input_tokens=total.input_tokens + attempt.input_tokens,
            output_tokens=total.output_tokens + attempt.output_tokens,
            cache_read_tokens=total.cache_read_tokens + attempt.cache_read_tokens,
            cache_write_tokens=0,
        )

    async def generate(self, request: LLMRequest) -> LLMResult:
        model = request.model or self._default_model
        return await self._run_structured(model, request, self._messages(request))

    async def _run_structured(
        self,
        model: str,
        request: LLMRequest | ToolLoopRequest,
        messages: list[dict[str, Any]],
        extra_kwargs: dict[str, Any] | None = None,
    ) -> LLMResult:
        """JSON-mode completion validated against request.output_schema, with
        the repair retry — shared by generate() and conclude()."""
        start = time.perf_counter()

        total = Usage()
        finish_reason = "stop"
        raw: Any = None
        parsed: BaseModel | None = None
        text = ""
        error_detail: str | None = None
        max_tokens = request.max_tokens

        for attempt in range(self._repair_attempts + 1):
            text, finish_reason, raw_usage, raw = await self._complete(
                model, request, messages, extra_kwargs, max_tokens=max_tokens
            )
            total = self._accumulate(total, self._usage(raw_usage))

            if finish_reason == "content_filter":
                break
            if finish_reason == "length":
                # Truncation, not a schema problem: retrying with the same
                # ceiling would truncate identically. Raise the ceiling and
                # retry the original messages (no repair turn appended).
                error_detail = f"truncated at max_tokens={max_tokens}"
                if attempt == self._repair_attempts or max_tokens >= _MAX_RETRY_MAX_TOKENS:
                    break
                max_tokens = min(max_tokens * 2, _MAX_RETRY_MAX_TOKENS)
                continue
            try:
                parsed = parse_payload(text, request.output_schema)
                error_detail = None
                break
            except (ValidationError, ValueError) as exc:
                error_detail = str(exc)[:2000]
                if attempt == self._repair_attempts:
                    break
                messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "That response did not validate against the required schema:\n"
                            f"{error_detail}\n\nReturn the corrected json object only."
                        ),
                    },
                ]

        if finish_reason == "content_filter":
            stop_reason = "refusal"
        elif parsed is None and finish_reason == "length":
            stop_reason = "truncated"
        elif parsed is None:
            stop_reason = "invalid_output"
        else:
            stop_reason = finish_reason

        return LLMResult(
            parsed=parsed,
            stop_reason=stop_reason,
            usage=total,
            cost_usd=_cost_usd(model, total),
            latency_ms=int((time.perf_counter() - start) * 1000),
            model=model,
            provider=self.name,
            raw=raw,
            raw_text=text if parsed is None else None,
            error_detail=error_detail if parsed is None else None,
        )

    # -- tool loop (llm/tools.py) ---------------------------------------

    @staticmethod
    def _tool_defs(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
            }
            for t in tools
        ]

    def _loop_messages(
        self, request: ToolLoopRequest, *, include_schema_block: bool
    ) -> list[dict[str, Any]]:
        """The schema block is appended only on the conclude turn — during
        exploration the model must feel free to emit tool calls and prose,
        not a premature json object."""
        blocks = list(request.system_blocks)
        if include_schema_block:
            blocks.append(schema_block(request.output_schema))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "\n\n".join(blocks)},
            {"role": "user", "content": request.user_content.text},
        ]
        for exchange in request.transcript:
            turn = exchange.turn
            if turn.raw is not None:
                messages.append(turn.raw)
            else:
                msg: dict[str, Any] = {"role": "assistant", "content": turn.text or None}
                if turn.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in turn.tool_calls
                    ]
                messages.append(msg)
            for outcome in exchange.outcomes:
                messages.append(
                    {"role": "tool", "tool_call_id": outcome.call_id, "content": outcome.content.text}
                )
        if request.turn_note:
            messages.append({"role": "user", "content": request.turn_note})
        return messages

    async def explore(self, request: ToolLoopRequest) -> ToolTurnResult:
        start = time.perf_counter()
        model = request.model or self._default_model

        # Thinking is deliberately NOT enabled on exploration turns:
        # DeepSeek's thinking mode does not support function calling. The
        # conclude turn has no tool calls to make and re-enables it.
        resp = await self._client.chat.completions.create(
            model=model,
            messages=self._loop_messages(request, include_schema_block=False),
            max_tokens=request.max_tokens,
            tools=self._tool_defs(request.tools),
            reasoning_effort=_EFFORT_MAP.get(request.effort, "high"),
        )
        choice = resp.choices[0]
        message = choice.message

        calls: list[ToolCall] = []
        for tc in message.tool_calls or []:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except ValueError:
                # Malformed arguments become an executable-but-failing call so
                # the toolbox can hand the model a correctable error.
                arguments = {"_malformed_arguments": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=arguments))

        if choice.finish_reason == "content_filter":
            stop_reason = "refusal"
        elif calls:
            stop_reason = "tool_use"
        else:
            stop_reason = choice.finish_reason or "stop"

        usage = self._usage(resp.usage)
        raw_message = message.model_dump(exclude_none=True)
        # DeepSeek rejects requests whose history contains reasoning_content.
        raw_message.pop("reasoning_content", None)
        turn = AssistantTurn(text=message.content or "", tool_calls=tuple(calls), raw=raw_message)
        return ToolTurnResult(
            turn=turn,
            result=LLMResult(
                parsed=None,
                stop_reason=stop_reason,
                usage=usage,
                cost_usd=_cost_usd(model, usage),
                latency_ms=int((time.perf_counter() - start) * 1000),
                model=model,
                provider=self.name,
                raw=resp,
            ),
        )

    async def conclude(self, request: ToolLoopRequest) -> LLMResult:
        model = request.model or self._default_model
        # tools + tool_choice="none" (rather than omitting tools) so the API
        # can resolve the tool_calls already present in the replayed history.
        extra: dict[str, Any] = {}
        if request.transcript:
            extra = {"tools": self._tool_defs(request.tools), "tool_choice": "none"}
        return await self._run_structured(
            model, request, self._loop_messages(request, include_schema_block=True), extra
        )
