"""Config-driven provider selection. Adding a fourth provider means adding
one branch here and one module under llm/providers/ — nothing else in the
codebase references a vendor SDK (domain, services, and agent nodes only
ever see the LLMProvider Protocol from llm/base.py)."""

from __future__ import annotations

from haaland.config import Settings
from haaland.llm.base import LLMProvider


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        from haaland.llm.providers.fake import FakeLLMProvider

        return FakeLLMProvider()

    if settings.llm_provider == "deepseek":
        if not settings.deepseek_api_key:
            raise RuntimeError("HAALAND_DEEPSEEK_API_KEY is required when llm_provider=deepseek")
        from haaland.llm.providers.deepseek import DeepSeekProvider

        return DeepSeekProvider(
            settings.deepseek_api_key,
            default_model=settings.model_primary,
            base_url=settings.deepseek_base_url,
        )

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("HAALAND_ANTHROPIC_API_KEY is required when llm_provider=anthropic")
        from haaland.llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider(settings.anthropic_api_key, default_model=settings.model_primary)

    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("HAALAND_OPENAI_API_KEY is required when llm_provider=openai")
        from haaland.llm.providers.openai import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key)

    raise ValueError(f"unknown llm_provider: {settings.llm_provider!r}")
