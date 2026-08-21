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
from haaland.llm.tools import (
    AssistantTurn,
    ToolCall,
    ToolExchange,
    ToolLoopRequest,
    ToolOutcome,
    ToolSpec,
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
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
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


def _provider(
    responses: list[SimpleNamespace], *, thinking: bool = True
) -> tuple[DeepSeekProvider, ScriptedCompletions]:
    provider = DeepSeekProvider("test-key", thinking=thinking)
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
    # The rejected reply is quoted back so the model can see what it got wrong…
    assert '{"severity": "P1"}' in repair_messages[-1]["content"]
    # …inside the user turn, never as an assistant echo: thinking mode rejects
    # an assistant message that carries no reasoning_content.
    assert [m["role"] for m in repair_messages] == ["system", "user"]
    # Both attempts are billed.
    assert result.usage.output_tokens == 100


async def test_unrepairable_output_is_not_silently_returned() -> None:
    provider, _ = _provider([_response("not json at all"), _response("still not json")])

    result = await provider.generate(_request())

    assert result.parsed is None
    assert result.stop_reason == "invalid_output"
    # The raw text and validation detail survive to the ai_analyses row, so a
    # truncation and a safety refusal are distinguishable after the fact.
    assert result.raw_text == "still not json"
    assert result.error_detail
    # LLMCallService raises AIInvalidOutputError on a None parse (and
    # AIRefusalError only on a real refusal), so the graph never sees a
    # half-parsed stage result.


async def test_truncation_retries_with_raised_ceiling_then_reports_truncated() -> None:
    provider, completions = _provider(
        [
            _response('{"severity": "P1"', finish_reason="length"),
            _response('{"severity": "P1"', finish_reason="length"),
        ]
    )

    result = await provider.generate(_request(max_tokens=2000))

    assert result.parsed is None
    assert result.stop_reason == "truncated"
    assert "truncated at max_tokens" in (result.error_detail or "")
    # The retry raised the ceiling instead of repeating the same truncation.
    assert completions.calls[0]["max_tokens"] == 2000
    assert completions.calls[1]["max_tokens"] == 4000
    # No repair turn was appended — truncation is not a schema problem.
    assert len(completions.calls[1]["messages"]) == len(completions.calls[0]["messages"])


async def test_truncation_retry_can_succeed() -> None:
    provider, completions = _provider(
        [
            _response('{"severity": "P', finish_reason="length"),
            _response('{"severity": "P1", "confidence": 0.9}'),
        ]
    )

    result = await provider.generate(_request(max_tokens=2000))

    assert result.parsed == Answer(severity="P1", confidence=0.9)
    assert result.stop_reason == "stop"
    assert completions.calls[1]["max_tokens"] == 4000


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
                SimpleNamespace(delta=SimpleNamespace(content='{"severity": "P3",'), finish_reason=None)
            ],
        )
        yield SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(delta=SimpleNamespace(content=' "confidence": 0.1}'), finish_reason="stop")
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
    assert usage == Usage(input_tokens=100, output_tokens=200, cache_read_tokens=900, cache_write_tokens=0)

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


# -- tool loop (explore/conclude) --------------------------------------------


def _tool_response(*, content: str | None = None, tool_calls=None, finish_reason: str = "stop"):
    class _Message:
        """SimpleNamespace can't model_dump(); the provider replays the raw
        assistant message, so the stub needs that method too."""

        def __init__(self) -> None:
            self.content = content
            self.tool_calls = tool_calls

        def model_dump(self, exclude_none: bool = False) -> dict:
            out: dict = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                out["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in self.tool_calls
                ]
            return out

    return SimpleNamespace(
        choices=[SimpleNamespace(message=_Message(), finish_reason=finish_reason)],
        usage=_usage(prompt_miss=100, completion=50),
    )


def _loop_request(transcript=None, **overrides) -> ToolLoopRequest:
    kwargs = dict(
        stage="diagnose",
        system_blocks=["base instructions", "stage instructions"],
        user_content=RedactedPayload("[REDACTED] log line"),
        output_schema=Answer,
        tools=[ToolSpec(name="grep", description="search", input_schema={"type": "object"})],
        transcript=transcript or [],
        max_tokens=4000,  # below the streaming threshold — the stub isn't a stream
    )
    kwargs.update(overrides)
    return ToolLoopRequest(**kwargs)


async def test_explore_parses_tool_calls_and_disables_thinking_and_json_mode() -> None:
    tool_call = SimpleNamespace(
        id="call_1", function=SimpleNamespace(name="grep", arguments='{"pattern": "len"}')
    )
    provider, completions = _provider(
        [_tool_response(content="looking", tool_calls=[tool_call], finish_reason="tool_calls")]
    )

    turn = await provider.explore(_loop_request())

    assert turn.turn.tool_calls == (ToolCall(id="call_1", name="grep", arguments={"pattern": "len"}),)
    assert turn.result.stop_reason == "tool_use"
    assert turn.result.parsed is None

    sent = completions.calls[0]
    # Function calling is incompatible with DeepSeek thinking mode, and JSON
    # mode must not gag the exploration turns.
    assert "extra_body" not in sent
    assert "response_format" not in sent
    assert sent["tools"][0]["function"]["name"] == "grep"
    # No schema block during exploration — only the conclude turn asks for json.
    assert "JSON Schema" not in sent["messages"][0]["content"]


async def test_explore_appends_turn_note_as_trailing_user_message() -> None:
    provider, completions = _provider([_tool_response(content="ok")])

    await provider.explore(_loop_request(turn_note="[loop status] exploration turns remaining: 3."))

    sent = completions.calls[0]
    assert sent["messages"][-1] == {
        "role": "user",
        "content": "[loop status] exploration turns remaining: 3.",
    }


def _explored(*, raw=None) -> list[ToolExchange]:
    return [
        ToolExchange(
            turn=AssistantTurn(
                text="looking",
                tool_calls=(ToolCall(id="call_1", name="grep", arguments={"pattern": "len"}),),
                raw=raw,
            ),
            outcomes=(
                ToolOutcome(call_id="call_1", name="grep", content=RedactedPayload("app/pricing.py:6: hit")),
            ),
        )
    ]


async def test_conclude_keeps_thinking_on_by_folding_the_transcript_into_the_user_turn() -> None:
    """The regression the 400 came from: exploration turns run without thinking,
    so their assistant messages carry no reasoning_content and cannot be replayed
    into the thinking-mode conclude call ("The `reasoning_content` in the thinking
    mode must be passed back to the API"). The evidence goes into the user turn
    instead, and thinking stays on for the turn that produces the diagnosis."""
    provider, completions = _provider([_response('{"severity": "P1", "confidence": 0.9}')])

    result = await provider.conclude(_loop_request(_explored()))

    assert result.parsed == Answer(severity="P1", confidence=0.9)
    sent = completions.calls[0]
    assert sent["extra_body"] == {"thinking": {"type": "enabled"}}
    assert sent["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in sent["messages"][0]["content"]
    # No assistant message anywhere — the only shape valid in thinking mode.
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]
    user = sent["messages"][1]["content"]
    assert "[REDACTED] log line" in user
    assert "looking" in user
    assert '`grep({"pattern": "len"})`' in user
    assert "app/pricing.py:6: hit" in user
    # Nothing left for the API to resolve, so no tool plumbing is sent either.
    assert "tools" not in sent and "tool_choice" not in sent


async def test_conclude_replays_natively_when_every_turn_carries_its_reasoning() -> None:
    """The other half of the rule: a transcript whose assistant turns *do* carry
    reasoning_content is replayable as-is, so the wire format the API produced is
    kept — including the reasoning it demands back."""
    raw = {
        "role": "assistant",
        "content": "looking",
        "reasoning_content": "the pool size is the suspect",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "grep", "arguments": '{"pattern": "len"}'},
            }
        ],
    }
    provider, completions = _provider([_response('{"severity": "P1", "confidence": 0.9}')])

    result = await provider.conclude(_loop_request(_explored(raw=raw)))

    assert result.parsed == Answer(severity="P1", confidence=0.9)
    sent = completions.calls[0]
    assert sent["extra_body"] == {"thinking": {"type": "enabled"}}
    assert sent["tool_choice"] == "none"
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "assistant", "tool"]
    assert sent["messages"][2]["reasoning_content"] == "the pool size is the suspect"
    assert sent["messages"][3] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "app/pricing.py:6: hit",
    }


async def test_conclude_replays_natively_when_thinking_is_off() -> None:
    provider, completions = _provider([_response('{"severity": "P1", "confidence": 0.9}')], thinking=False)

    await provider.conclude(_loop_request(_explored()))

    sent = completions.calls[0]
    assert "extra_body" not in sent
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "assistant", "tool"]


async def test_explore_drops_reasoning_from_replayed_turns() -> None:
    """Exploration runs without thinking, and a non-thinking request rejects
    reasoning_content — so the same stored turn is rendered without it here."""
    raw = {"role": "assistant", "content": "looking", "reasoning_content": "a thought"}
    provider, completions = _provider([_tool_response(content="still looking")])

    await provider.explore(_loop_request([ToolExchange(turn=AssistantTurn(text="looking", raw=raw))]))

    replayed = completions.calls[0]["messages"][2]
    assert replayed == {"role": "assistant", "content": "looking"}


async def test_explore_keeps_reasoning_on_the_stored_turn() -> None:
    """Stripping at capture time (rather than at render time) would make a
    thinking-mode replay impossible after the fact."""

    class _Message:
        content = "looking"
        tool_calls = None

        def model_dump(self, exclude_none: bool = False) -> dict:
            return {"role": "assistant", "content": "looking", "reasoning_content": "a thought"}

    provider, _ = _provider(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(message=_Message(), finish_reason="stop")],
                usage=_usage(prompt_miss=10, completion=5),
            )
        ]
    )

    turn = await provider.explore(_loop_request())

    assert turn.turn.raw["reasoning_content"] == "a thought"
