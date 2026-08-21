"""Service health, derived — never stored.

There is no health column and no health check: a service's pill is a function
of the incidents currently open against it. Keeping the rule here (pure, no
session, no ORM row) is what lets it be unit-tested and keeps the dashboard
and any future notifier from drifting into two different definitions of
"unhealthy".
"""

from __future__ import annotations

from typing import Literal

from haaland.domain.enums import RESOLVED_STATUSES, IncidentStatus, Severity

Health = Literal["healthy", "p1", "p2"]


def is_active(status: str) -> bool:
    try:
        return IncidentStatus(status) not in RESOLVED_STATUSES
    except ValueError:  # a status the enum does not know about is not "resolved"
        return True


def derive_health(incidents: list[tuple[str, str | None]]) -> Health:
    """`incidents` is (status, severity) for every incident on the service.

    P1 wins over everything; any other open incident — including one not yet
    classified, which is most of a run's lifetime — shows as P2 rather than
    green, because an unclassified incident is still an unresolved one.
    """
    active = [severity for status, severity in incidents if is_active(status)]
    if not active:
        return "healthy"
    if any(severity == Severity.P1.value for severity in active):
        return "p1"
    return "p2"
