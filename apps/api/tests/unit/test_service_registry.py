"""The registry's derived fields — the part the dashboard renders and the
part with no database in it. Health is a pure function of the incidents on a
service (domain/health.py); `_to_read` is the mapping the list endpoint
applies to every row."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from haaland.api.routes.services import _to_read
from haaland.domain.health import derive_health, is_active


def _incident(status: str, severity: str | None = None, *, reference: str = "INC-2026-0001"):
    return SimpleNamespace(
        reference=reference,
        title="Debug session — orders-api",
        status=status,
        severity=severity,
        detected_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        closed_at=None,
    )


def _service(**overrides):
    base = {
        "id": uuid.uuid4(),
        "name": "orders-api",
        "repo_full_name": "haaland-demo/orders-api",
        "tier": 1,
        "owner_team": "Team Orders",
        "runbook_url": None,
        "metadata_": {"base_ref": "main", "repo_url": "https://github.com/haaland-demo/orders-api"},
        "created_at": datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    }
    return SimpleNamespace(**{**base, **overrides})


def test_no_incidents_is_healthy():
    assert derive_health([]) == "healthy"


def test_only_resolved_incidents_is_healthy():
    assert derive_health([("closed", "P1"), ("triaged_low", "P4"), ("rejected", "P2")]) == "healthy"


def test_open_p1_wins_over_everything():
    assert derive_health([("closed", "P4"), ("remediating", "P1"), ("diagnosing", "P3")]) == "p1"


def test_unclassified_open_incident_is_not_green():
    # Most of a run's life is spent before the classifier assigns a severity;
    # a service with a live run must not read as healthy in that window.
    assert derive_health([("detected", None)]) == "p2"


def test_failed_and_escalated_runs_still_count_as_open():
    # Neither status resolves the incident — one died mid-run, the other is
    # parked waiting on a human.
    assert is_active("failed") is True
    assert is_active("escalated") is True
    assert derive_health([("failed", "P1")]) == "p1"


def test_unknown_status_is_treated_as_open():
    assert is_active("some_future_status") is True


def test_to_read_maps_counts_and_latest_incident():
    incidents = [
        _incident("remediating", "P1", reference="INC-2026-0007"),
        _incident("closed", "P3", reference="INC-2026-0002"),
    ]
    read = _to_read(_service(), incidents)

    assert read.health == "p1"
    assert read.incident_count == 2
    assert read.active_incident_count == 1
    assert read.last_incident is not None
    # The repository orders newest-first; [0] is the card's "last incident".
    assert read.last_incident.reference == "INC-2026-0007"
    assert read.base_ref == "main"
    assert read.repo_url == "https://github.com/haaland-demo/orders-api"


def test_to_read_falls_back_to_repo_full_name_and_default_branch():
    read = _to_read(_service(metadata_={}), [])

    assert read.repo_url == "https://github.com/haaland-demo/orders-api"
    assert read.base_ref == "main"
    assert read.health == "healthy"
    assert read.last_incident is None


def test_to_read_handles_a_service_with_no_repository():
    read = _to_read(_service(repo_full_name=None, metadata_={}), [])

    assert read.repo_url is None
    assert read.repo_full_name is None
