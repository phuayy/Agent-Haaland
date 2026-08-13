"""The regression net for the entire compliance claim (docs/03's own
words). If this drifts, every previously recorded incident's chain breaks
verification, so `compute_hash`'s determinism and tamper-sensitivity are
tested directly, without a database."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from haaland.db.repositories.events import compute_hash

_INCIDENT_ID = uuid4()


def _base_kwargs():
    return dict(
        prev_hash=None,
        incident_id=_INCIDENT_ID,
        seq=1,
        event_type="incident.opened",
        actor_type="system",
        actor_label="api",
        summary="Incident opened",
        payload={"b": 2, "a": 1},
        occurred_at=datetime(2026, 8, 13, 9, 11, 40, 201000, tzinfo=UTC),
    )


def test_hash_is_deterministic():
    kwargs = _base_kwargs()
    assert compute_hash(**kwargs) == compute_hash(**kwargs)


def test_payload_key_order_does_not_affect_hash():
    """RFC 8785 canonicalisation: {"a":1,"b":2} and {"b":2,"a":1} must hash
    identically — this is the exact bug docs/03 warns json.dumps has."""
    kwargs_a = _base_kwargs()
    kwargs_a["payload"] = {"a": 1, "b": 2}
    kwargs_b = _base_kwargs()
    kwargs_b["payload"] = {"b": 2, "a": 1}
    assert compute_hash(**kwargs_a) == compute_hash(**kwargs_b)


def test_changing_any_field_changes_the_hash():
    baseline = compute_hash(**_base_kwargs())

    for field, value in [
        ("event_type", "incident.closed"),
        ("actor_label", "someone-else"),
        ("summary", "different summary"),
        ("seq", 2),
    ]:
        kwargs = _base_kwargs()
        kwargs[field] = value
        assert compute_hash(**kwargs) != baseline, f"{field} did not affect the hash"


def test_prev_hash_chains_into_next_hash():
    first = compute_hash(**_base_kwargs())
    second_kwargs = _base_kwargs()
    second_kwargs["seq"] = 2
    second_kwargs["prev_hash"] = first
    third_kwargs = _base_kwargs()
    third_kwargs["seq"] = 2
    third_kwargs["prev_hash"] = b"\x00" * 32  # wrong prev_hash

    assert compute_hash(**second_kwargs) != compute_hash(**third_kwargs)
