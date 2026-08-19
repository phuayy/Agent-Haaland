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

Thinking is opt-in per request: `extra_body={"thinking": {"type": "enabled"}}`.
`reasoning_effort` is `low | high | max` (default `high`) — note there is no
`medium`, so the provider-neutral `LLMRequest.effort` is mapped
`low -> low`, `medium -> high`, `high -> max` in `_EFFORT_MAP`.

## Caching and cost

The context cache is implicit — no breakpoints to place, nothing charged to write.
Usage comes back split as `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`,
mapped onto `Usage.cache_read_tokens` / `Usage.input_tokens` so `ai_analyses` rows
stay comparable across providers.

Pricing is time-of-day dependent (peak 01:00-04:00 and 06:00-10:00 UTC costs 2x
off-peak), so `_cost_usd` picks a rate table by current UTC hour. It is an estimate
for `BudgetGuard`, not a billing record — the same budget ceilings buy roughly an
order of magnitude more calls than on the Anthropic path.
