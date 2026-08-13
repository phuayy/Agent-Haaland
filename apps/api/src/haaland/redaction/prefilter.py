"""Deterministic pre-pass. Runs unconditionally — even when the Presidio
engine is selected — so a spaCy model update can never silently drop
coverage on the highest-severity patterns (docs/05)."""

from __future__ import annotations

from haaland.redaction.recognizers import INJECTION_MARKERS, RECOGNIZERS


def redact_text(text: str, counters: dict[str, int] | None = None) -> str:
    """Stateless convenience redaction for logging (logging.py). Tokens are
    only stable within a single call — incident-scoped stable tokens live in
    redaction/service.py + vault.py, which this function does not replace."""
    counters = counters if counters is not None else {}
    out = text
    for rec in RECOGNIZERS:
        def _sub(match, rec=rec):
            value = match.group(0)
            if rec.validator and not rec.validator(value):
                return value
            counters[rec.entity] = counters.get(rec.entity, 0) + 1
            return f"<{rec.entity}_{counters[rec.entity]}>"

        out = rec.pattern.sub(_sub, out)
    return out


def detect_injection(text: str) -> bool:
    """Flag, never filter — filtering degrades diagnosis and the attacker
    just varies phrasing (docs/09)."""
    return any(pattern.search(text) for pattern in INJECTION_MARKERS)
