# DeepSeek envelope

Default real provider. `prompts/system/base.md` + `prompts/<stage>/instructions.md`
are joined into a single `system` message, followed by one generated block
carrying the JSON Schema of the stage's Pydantic output model. See
`llm/providers/deepseek.py`.

## Why the OpenAI surface and not the Anthropic one

DeepSeek publishes both:

| | OpenAI-compatible | Anthropic-compatible |
|---|---|---|
| base_url | `https://api.deepseek.com` | `https://api.deepseek.com/anthropic` |
| SDK | `openai` | `anthropic` |
| model names | `deepseek-v4-flash`, `deepseek-v4-pro` | `claude-*` names, silently remapped |

The Anthropic surface looks like a zero-code swap (point `AnthropicProvider` at a
different `base_url`) but it is the wrong choice here:

- It has no equivalent of Anthropic's structured-output path — `messages.parse()` /
  `output_format=<PydanticModel>` — which every stage of this pipeline depends on.
- It ignores `cache_control`, so the cache breakpoint `AnthropicProvider` places on
  the last stable system block does nothing.
- It remaps model names by prefix (`claude-opus*` -> `deepseek-v4-pro`, everything
  else -> `deepseek-v4-flash`), including names it does not recognise. A typo
  downgrades the model instead of erroring.

## Structured output

DeepSeek's JSON mode is `response_format={"type": "json_object"}` — valid JSON is
guaranteed, conformance to *your* schema is not (there is no strict `json_schema`
mode). So the envelope:

1. appends the schema as a final system block, with the literal word "json" in it
   (DeepSeek requires the word to appear in the prompt for JSON mode to engage);
2. validates the response with `output_schema.model_validate_json`;
3. on `ValidationError`, sends one repair turn quoting the error, then gives up
   with `stop_reason="invalid_output"` (which `LLMCallService` surfaces as
   `AIRefusalError`, same as a refusal).

## Thinking and effort

Thinking is opt-in per request: `extra_body={"thinking": {"type": "enabled"}}`,
on by default for the structured (deliverable) calls and switchable with
`HAALAND_DEEPSEEK_THINKING`. `reasoning_effort` is `low | high | max` (default
`high`) — note there is no `medium`, so the provider-neutral `LLMRequest.effort`
is mapped `low -> low`, `medium -> high`, `high -> max` in `_EFFORT_MAP`.

Thinking mode is **stateful across turns**, which constrains message shape:

| | assistant message with `reasoning_content` | assistant message without |
|---|---|---|
| thinking on | accepted | **400** `The 'reasoning_content' in the thinking mode must be passed back to the API.` |
| thinking off | **400** | accepted |

Exploration turns run with thinking *off* (function calling and thinking are
mutually exclusive here), so their assistant messages have no reasoning to hand
back. Rather than downgrade the turn that actually produces the diagnosis, every
request that would need such a replay is built with **no assistant message at
all**:

- **conclude** — the exploration transcript is folded into the user turn as an
  evidence digest (`render_transcript_digest`): same thoughts, tool calls and
  redacted tool output, `tools`/`tool_choice` omitted because there are no
  `tool_calls` left for the API to resolve. Should a transcript ever arrive with
  reasoning on every turn, `transcript_is_thinking_replayable` picks the native
  assistant/tool replay again and passes the reasoning back untouched.
- **repair** — the rejected reply is quoted inside the trailing user message
  instead of being echoed as an assistant turn.

`AssistantTurn.raw` keeps `reasoning_content` when the model returns one;
`_replay_assistant` strips it per-request, so the same stored turn is legal in
either mode.

Budget consequence: reasoning tokens are billed as output **and** count against
`max_tokens`, which is why the tool loop concludes at `_CONCLUDE_MAX_TOKENS =
24000` (and why `finish_reason="length"` retries by doubling the ceiling rather
than repeating the call). Anything at or above `_STREAM_ABOVE_MAX_TOKENS = 8000`
streams, so a long reasoning pass cannot trip an idle-timeout reset; the arq
ceiling for the whole job is `HAALAND_ARQ_JOB_TIMEOUT_SECONDS` (default 1800s).

## Caching and cost

The context cache is implicit — no breakpoints to place, nothing charged to write.
Usage comes back split as `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`,
mapped onto `Usage.cache_read_tokens` / `Usage.input_tokens` so `ai_analyses` rows
stay comparable across providers.

Pricing is time-of-day dependent (peak 01:00-04:00 and 06:00-10:00 UTC costs 2x
off-peak), so `_cost_usd` picks a rate table by current UTC hour. It is an estimate
for `BudgetGuard`, not a billing record — the same budget ceilings buy roughly an
order of magnitude more calls than on the Anthropic path.
