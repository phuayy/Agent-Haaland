# OpenAI envelope

`prompts/<stage>/instructions.md` + `system/base.md` are joined into a single
`system` message (OpenAI has no multi-block system prompt or the same
cache-control primitive as Anthropic's `cache_control` — the closest
equivalent is automatic prefix caching, which needs no explicit marker).
Structured output uses `response_format=<PydanticModel>` via
`chat.completions.parse`. See `llm/providers/openai.py`.

Adding a real prompt-cache-equivalent optimisation here (e.g. reordering to
maximise OpenAI's automatic prefix cache hit rate) is future work — flagged
so a cost audit doesn't assume parity with the Anthropic path.
