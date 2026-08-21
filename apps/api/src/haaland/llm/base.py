"""Provider-agnostic LLM boundary. Every provider — Anthropic, OpenAI, the
offline fake — implements this Protocol and returns the same result shape,
which is what lets `ai_analyses` stay provider-independent and lets a new
provider be added as one module plus one template directory.

The type boundary in `RedactedPayload` is deliberate (docs/09): there is no
overload of `LLMProvider.generate` that accepts a raw string. A new engineer
cannot accidentally send unredacted evidence to a model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class RedactedPayload:
    """Marker type: text that has already passed through Redactor. Construct
    this only from redaction/service.py."""

    text: str


@dataclass
class LLMRequest:
    stage: str  # 'classify' | 'diagnose' | 'evaluate' | 'remediate' | 'test' | 'report'
    system_blocks: list[str]  # provider-neutral instruction blocks, stable-prefix first
    user_content: RedactedPayload
    output_schema: type[BaseModel]
    effort: Literal["low", "medium", "high"] = "medium"
    max_tokens: int = 8000
    model: str | None = None  # None -> provider picks its default for this stage


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class LLMResult:
    parsed: BaseModel | None
    stop_reason: str
    usage: Usage
    cost_usd: float
    latency_ms: int
    model: str
    provider: str
    raw: Any = field(default=None, repr=False)
    # Set only when parsed is None for a non-refusal reason: the model's raw
    # text plus the validation/truncation detail, so the ai_analyses row can
    # distinguish a truncation from a safety refusal after the fact.
    raw_text: str | None = field(default=None, repr=False)
    error_detail: str | None = None

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "truncated"


class LLMProvider(Protocol):
    name: str

    async def generate(self, request: LLMRequest) -> LLMResult: ...
