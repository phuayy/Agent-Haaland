"""Load, hash, and version stage instruction files. Prompts are provider-
neutral markdown under apps/api/prompts/; the vendor envelope (where the
cache breakpoint goes, how structured output is requested) lives in
llm/templates/<provider>/ instead — see llm/registry.py. Changing a prompt
file changes its hash, which is recorded on every ai_analyses row, which is
what answers an auditor's "which exact instructions produced this decision"
question (docs/03, docs/05)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PROMPTS_ROOT = Path(__file__).resolve().parents[3] / "prompts"


@dataclass(frozen=True)
class Prompt:
    stage: str
    version: str
    text: str
    sha256: bytes

    @property
    def qualified_version(self) -> str:
        return f"{self.stage}@{self.version}"


@lru_cache
def load_prompt(relative_path: str) -> Prompt:
    path = _PROMPTS_ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    stage = relative_path.split("/")[0]
    version = f"v{digest.hex()[:8]}"
    return Prompt(stage=stage, version=version, text=text, sha256=digest)


def load_system_base() -> Prompt:
    return load_prompt("system/base.md")


def load_stage_instructions(stage: str) -> Prompt:
    return load_prompt(f"{stage}/instructions.md")
