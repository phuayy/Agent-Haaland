# Generic / self-hosted envelope (Phase 6 placeholder)

Target for a self-hosted OpenAI-compatible endpoint (vLLM, etc.) per
docs/02 section 4's "Alternatives" note on zero-egress deployments. Not
implemented — `llm/providers/openai.py` is close enough in shape (OpenAI's
client already speaks the OpenAI-compatible wire format most self-hosted
servers implement) that standing this up is expected to be a subclass with a
different `base_url`, not a new envelope.
