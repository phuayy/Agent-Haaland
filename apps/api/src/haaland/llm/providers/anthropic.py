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
"""

from __future__ import annotations

import time

import anthropic

from haaland.llm.base import LLMRequest, LLMResult, Usage

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

    def _system_blocks(self, request: LLMRequest) -> list[dict]:
        blocks = []
        for i, text in enumerate(request.system_blocks):
            block: dict = {"type": "text", "text": text}
            if i == len(request.system_blocks) - 1:
                block["cache_control"] = {"type": "ephemeral"}
            blocks.append(block)
        return blocks

    async def generate(self, request: LLMRequest) -> LLMResult:
        start = time.perf_counter()
        model = request.model or self._default_model
        effort = request.effort or _EFFORT_BY_STAGE.get(request.stage, "medium")

        kwargs = dict(
            model=model,
            max_tokens=request.max_tokens,
            system=self._system_blocks(request),
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

        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.stop_reason == "refusal":
            usage = Usage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
            )
            return LLMResult(
                parsed=None,
                stop_reason="refusal",
                usage=usage,
                cost_usd=_cost_usd(model, usage),
                latency_ms=latency_ms,
                model=model,
                provider=self.name,
                raw=resp,
            )

        usage = Usage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        )
        return LLMResult(
            parsed=resp.parsed_output,
            stop_reason=resp.stop_reason,
            usage=usage,
            cost_usd=_cost_usd(model, usage),
            latency_ms=latency_ms,
            model=model,
            provider=self.name,
            raw=resp,
        )
