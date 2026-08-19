"""DeepSeek is the default real provider, and the only one whose structured
output is enforced in our code rather than by the vendor. These tests pin the
three things that carry that weight: the schema block reaches the model, an
off-schema response is repaired rather than propagated, and cache-split usage
is priced the way BudgetGuard expects.

No network: the OpenAI client is replaced with a scripted stub, per docs/02's
"never hit the API in CI"."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from haaland.llm.base import LLMRequest, RedactedPayload, Usage
from haaland.llm.providers.deepseek import (
    DeepSeekProvider,
    _cost_usd,
    extract_json,
    schema_block,
)


class Answer(BaseModel):
    severity: str
    confidence: float


def _usage(prompt_hit: int = 0, prompt_miss: int = 0, completion: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=prompt_hit + prompt_miss,
        prompt_cache_hit_tokens=prompt_hit,
        prompt_cache_miss_tokens=prompt_miss,
        completion_tokens=completion,
    )


def _response(content: str, *, finish_reason: str = "stop", usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason=finish_reason
            )
        ],
        usage=usage if usage is not None else _usage(prompt_miss=100, completion=50),
    )


class ScriptedCompletions:
    """Records every kwargs it is called with and replays queued responses."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _provider(responses: list[SimpleNamespace]) -> tuple[DeepSeekProvider, ScriptedCompletions]:
    provider = DeepSeekProvider("test-key")
    completions = ScriptedCompletions(responses)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return provider, completions


def _request(**overrides) -> LLMRequest:
    kwargs = dict(
        stage="classify",
        system_blocks=["base instructions", "stage instructions"],
        user_content=RedactedPayload("[REDACTED] log line"),
        output_schema=Answer,
        effort="medium",
        max_tokens=4000,
    )
    kwargs.update(overrides)
    return LLMRequest(**kwargs)


def test_schema_block_names_json_and_required_properties() -> None:
    block = schema_block(Answer)
    # DeepSeek only engages JSON mode when the word "json" appears in the prompt.
    assert "json" in block
    assert "severity" in block and "confidence" in block


@pytest.mark.parametrize(
    "raw",
    [
        '{"severity": "P1", "confidence": 0.9}',
        '```json\n{"severity": "P1", "confidence": 0.9}\n```',
        'Here you go:\n{"severity": "P1", "confidence": 0.9}\nHope that helps.',
    ],
)
def test_extract_json_tolerates_fences_and_preamble(raw: str) -> None:
    assert extract_json(raw) == '{"severity": "P1", "confidence": 0.9}'


async def test_generate_parses_and_sends_deepseek_params() -> None:
    provider, completions = _provider([_response('{"severity": "P1", "confidence": 0.9}')])

    result = await provider.generate(_request())

    assert isinstance(result.parsed, Answer)
    assert result.parsed.severity == "P1"
    assert result.stop_reason == "stop"
    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-flash"

    sent = completions.calls[0]
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["extra_body"] == {"thinking": {"type": "enabled"}}
    # "medium" is not in DeepSeek's low|high|max scale and must be mapped.
    assert sent["reasoning_effort"] == "high"
    assert "stream" not in sent
    system = sent["messages"][0]["content"]
    assert system.startswith("base instructions")
    assert "JSON Schema" in system


async def test_off_schema_response_triggers_one_repair_turn() -> None:
    provider, completions = _provider(
        [
            _response('{"severity": "P1"}'),  # missing required `confidence`
            _response('{"severity": "P1", "confidence": 0.4}'),
        ]
    )

    result = await provider.generate(_request())

    assert result.parsed == Answer(severity="P1", confidence=0.4)
    assert len(completions.calls) == 2
    repair_messages = completions.calls[1]["messages"]
    assert repair_messages[-1]["role"] == "user"
    assert "did not validate" in repair_messages[-1]["content"]
    # Both attempts are billed.
    assert result.usage.output_tokens == 100


async def test_unrepairable_output_is_not_silently_returned() -> None:
    provider, _ = _provider([_response("not json at all"), _response("still not json")])

    result = await provider.generate(_request())

    assert result.parsed is None
    assert result.stop_reason == "invalid_output"
    # LLMCallService raises AIRefusalError on a None parse, so the graph never
    # sees a half-parsed stage result.


async def test_content_filter_maps_to_refusal_without_repair() -> None:
    provider, completions = _provider([_response("", finish_reason="content_filter")])

    result = await provider.generate(_request())

    assert result.refused
    assert len(completions.calls) == 1


async def test_long_max_tokens_streams() -> None:
    async def stream_events():
        yield SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content='{"severity": "P3",'), finish_reason=None
                )
            ],
        )
        yield SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=' "confidence": 0.1}'), finish_reason="stop"
                )
            ],
        )
        yield SimpleNamespace(usage=_usage(prompt_miss=10, completion=20), choices=[])

    provider, completions = _provider([stream_events()])

    result = await provider.generate(_request(stage="report", max_tokens=20000))

    assert result.parsed == Answer(severity="P3", confidence=0.1)
    assert completions.calls[0]["stream"] is True
    assert result.usage.output_tokens == 20


def test_usage_splits_cache_hits_and_prices_them_apart() -> None:
    provider, _ = _provider([])

    usage = provider._usage(_usage(prompt_hit=900, prompt_miss=100, completion=200))

    # input_tokens means "uncached input" on every provider, so ai_analyses rows
    # stay comparable.
    assert usage == Usage(
        input_tokens=100, output_tokens=200, cache_read_tokens=900, cache_write_tokens=0
    )

    off_peak = _cost_usd("deepseek-v4-flash", usage, peak=False)
    peak = _cost_usd("deepseek-v4-flash", usage, peak=True)
    expected = (900 * 0.007 + 100 * 0.22 + 200 * 0.66) / 1_000_000
    assert off_peak == pytest.approx(round(expected, 6))
    assert peak == pytest.approx(round(expected * 2, 6))


def test_usage_without_cache_fields_counts_everything_as_a_miss() -> None:
    provider, _ = _provider([])

    usage = provider._usage(SimpleNamespace(prompt_tokens=500, completion_tokens=10))

    assert usage.input_tokens == 500
    assert usage.cache_read_tokens == 0
