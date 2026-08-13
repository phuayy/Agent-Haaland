"""The test that guards the redaction boundary (docs/05). Every canary here
must never appear in what the model would receive. A failure here is a
release blocker, not a flaky test to retry."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from haaland.domain.models import EvidenceBundle, LogLine

_NOW = datetime.now(UTC)

CANARIES = [
    "4532015112830366",
    "ACC-8829301",
    "GB33BUKB20201555555555",
    "priya.n@customer.example",
    "+65 9123 4567",
]


def _bundle_with(text: str) -> EvidenceBundle:
    return EvidenceBundle(
        incident_id=uuid4(),
        service_name="orders-api",
        repo_full_name="acme/orders-api",
        base_ref="main",
        log_lines=[LogLine(timestamp=_NOW, level="ERROR", message=text)],
    )


@pytest.mark.parametrize("canary", CANARIES)
async def test_canary_never_reaches_model(canary, redactor):
    bundle = _bundle_with(f"payment failed for {canary}")
    redacted, result = await redactor.redact_bundle(uuid4(), bundle)

    assert canary not in redacted.model_dump_json()
    assert sum(result.entity_counts.values()) >= 1


async def test_trace_id_is_not_redacted(redactor):
    """docs/05: over-redaction is a real failure mode — a trace_id-shaped
    hex string must survive, or the model loses the ability to correlate."""
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"  # 32 hex chars, not a card/account shape
    bundle = _bundle_with(f"trace_id={trace_id} latency=812ms")
    redacted, _ = await redactor.redact_bundle(uuid4(), bundle)

    assert trace_id in redacted.log_lines[0].message


async def test_stable_tokens_within_incident(redactor):
    """The same account number appearing twice must become the same token —
    otherwise the model can't reason about 'the same customer' across
    fields (docs/05)."""
    incident_id = uuid4()
    bundle = EvidenceBundle(
        incident_id=incident_id,
        service_name="orders-api",
        repo_full_name="acme/orders-api",
        base_ref="main",
        log_lines=[
            LogLine(
                timestamp=_NOW,
                level="ERROR",
                message="account ACC-8829301 failed",
            ),
            LogLine(
                timestamp=_NOW,
                level="ERROR",
                message="retrying account ACC-8829301",
            ),
        ],
    )
    redacted, _ = await redactor.redact_bundle(incident_id, bundle)

    first_token = redacted.log_lines[0].message.split("account ")[1].split(" failed")[0]
    second_token = redacted.log_lines[1].message.split("account ")[1]
    assert first_token == second_token
    assert first_token.startswith("<BANK_ACCOUNT")
