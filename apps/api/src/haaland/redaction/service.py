"""The redaction boundary as a single choke point. Nothing reaches the model
before this runs (docs/05). Tokens are stable within an incident: the same
account number appearing in a log line and a code excerpt both become
<ACCOUNT_1>, so the model can reason about "the same customer" across
sources without ever seeing the value."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from haaland.domain.models import EvidenceBundle, RedactionResult
from haaland.redaction.recognizers import RECOGNIZERS
from haaland.redaction.vault import TokenVault


class Redactor:
    def __init__(self, vault: TokenVault, *, presidio_analyze: Callable[[str], list] | None = None):
        self._vault = vault
        self._presidio_analyze = presidio_analyze  # injected only when engine=presidio

    def _tokenize(self, text: str, mapping: dict[str, str], counters: dict[str, int]) -> str:
        reverse = {v: k for k, v in mapping.items()}
        out = text
        for rec in RECOGNIZERS:
            def _sub(match, rec=rec):
                value = match.group(0)
                if rec.validator and not rec.validator(value):
                    return value
                if value in reverse:
                    return reverse[value]
                counters[rec.entity] = counters.get(rec.entity, 0) + 1
                token = f"<{rec.entity}_{counters[rec.entity]}>"
                mapping[token] = value
                reverse[value] = token
                return token

            out = rec.pattern.sub(_sub, out)
        return out

    def _tokenize_obj(self, obj, mapping: dict[str, str], counters: dict[str, int]):
        """Recursive walk for structured evidence (deploy context and any
        future dict-shaped source): every string leaf goes through the same
        tokenizer as log lines. Commit author emails are the obvious leak
        this closes — a deploy record is user-controlled content too."""
        if isinstance(obj, str):
            return self._tokenize(obj, mapping, counters)
        if isinstance(obj, dict):
            return {k: self._tokenize_obj(v, mapping, counters) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._tokenize_obj(v, mapping, counters) for v in obj]
        return obj

    async def redact_bundle(
        self, incident_id: uuid.UUID, bundle: EvidenceBundle
    ) -> tuple[EvidenceBundle, RedactionResult]:
        mapping: dict[str, str] = {}
        counters: dict[str, int] = {}

        redacted_lines = [
            line.model_copy(update={"message": self._tokenize(line.message, mapping, counters)})
            for line in bundle.log_lines
        ]

        # docs/05: service names, error class names, module paths, trace/span ids,
        # commit SHAs, HTTP status codes, latency numbers are diagnostic signal —
        # never redacted. Only log message bodies and code excerpts pass through
        # the tokenizer; code candidates keep their path/line but their snippet
        # is tokenized in case a secret literal or PII leaked into a string.
        redacted_candidates = [
            c.model_copy(update={"snippet": self._tokenize(c.snippet, mapping, counters)})
            for c in bundle.code_candidates
        ]

        redacted_deploys = [
            self._tokenize_obj(d, mapping, counters) for d in bundle.deploy_context
        ]

        redacted_bundle = bundle.model_copy(
            update={
                "log_lines": redacted_lines,
                "code_candidates": redacted_candidates,
                "deploy_context": redacted_deploys,
            }
        )

        vault_key = await self._vault.write(incident_id, mapping)
        entity_counts: dict[str, int] = {}
        for token in mapping:
            entity = token.strip("<>").rsplit("_", 1)[0]
            entity_counts[entity] = entity_counts.get(entity, 0) + 1

        result = RedactionResult(
            text=redacted_bundle.model_dump_json(), vault_key=vault_key, entity_counts=entity_counts
        )
        return redacted_bundle, result
