"""Second provider, proving the abstraction isn't Anthropic-shaped by
accident. Not the default and not as deeply tuned as anthropic.py (no
prompt-cache equivalent wired here) — this is the template a team adds a
third provider from, per the project's "modularise the LLM layer" goal."""

from __future__ import annotations

import time

from openai import AsyncOpenAI

from haaland.llm.base import LLMRequest, LLMResult, Usage

_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5": (5.0, 15.0),
    "gpt-5-mini": (0.5, 2.0),
}


def _cost_usd(model: str, usage: Usage) -> float:
    input_price, output_price = _PRICING.get(model, (5.0, 15.0))
    cost = (usage.input_tokens * input_price + usage.output_tokens * output_price) / 1_000_000
    return round(cost, 6)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, *, default_model: str = "gpt-5") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._default_model = default_model

    async def generate(self, request: LLMRequest) -> LLMResult:
        start = time.perf_counter()
        model = request.model or self._default_model

        resp = await self._client.chat.completions.parse(
            model=model,
            max_completion_tokens=request.max_tokens,
            messages=[
                {"role": "system", "content": "\n\n".join(request.system_blocks)},
                {"role": "user", "content": request.user_content.text},
            ],
            response_format=request.output_schema,
        )

        latency_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0]
        refused = choice.message.refusal is not None

        usage = Usage(
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )
        return LLMResult(
            parsed=None if refused else choice.message.parsed,
            stop_reason="refusal" if refused else (choice.finish_reason or "stop"),
            usage=usage,
            cost_usd=_cost_usd(model, usage),
            latency_ms=latency_ms,
            model=model,
            provider=self.name,
            raw=resp,
        )
