# Anthropic envelope

How provider-neutral prompt blocks (`prompts/<stage>/instructions.md`) become
an Anthropic `messages.parse()` call. Implemented in
`llm/providers/anthropic.py::AnthropicProvider._system_blocks` — kept as code
rather than a template file because the only per-call variation is *which*
block gets `cache_control`, which is a one-line rule, not a layout.

- `system` is a list of text blocks: `[base.md, stage instructions]`. The
  **last** block gets `cache_control: {"type": "ephemeral"}` — it must be the
  most stable one, so `LLMRequest.system_blocks` is ordered stable-first.
- `output_format` is the Pydantic schema directly — no JSON-in-a-string
  parsing.
- `thinking={"type": "adaptive"}` + `output_config={"effort": ...}`, never
  `temperature`/`top_p`/`top_k`/`budget_tokens`.
- `messages.stream()` when `max_tokens > 16000` (post-mortem generation).
