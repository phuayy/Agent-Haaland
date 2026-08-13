"""Legal incident-status transitions. Enforced at the service layer — see
services/incident_service.py — not merely discouraged. Mirrors the state
diagram in docs/01-architecture.md."""

from __future__ import annotations

from haaland.domain.enums import IncidentStatus as S
from haaland.domain.errors import IllegalTransition

_LEGAL: dict[S, set[S]] = {
    S.DETECTED: {S.ENRICHING, S.FAILED},
    S.ENRICHING: {S.TRIAGING, S.FAILED},
    S.TRIAGING: {S.TRIAGED_LOW, S.DIAGNOSING, S.FAILED},
    S.TRIAGED_LOW: {S.CLOSED},
    S.DIAGNOSING: {S.AWAITING_APPROVAL, S.FAILED},
    S.AWAITING_APPROVAL: {S.APPROVED, S.REJECTED, S.ESCALATED},
    S.ESCALATED: {S.AWAITING_APPROVAL},
    S.REJECTED: {S.DIAGNOSING, S.CLOSED},
    S.APPROVED: {S.REMEDIATING},
    S.REMEDIATING: {S.VERIFYING},
    S.VERIFYING: {S.REMEDIATING, S.DOCUMENTING},
    S.DOCUMENTING: {S.CLOSED},
    S.FAILED: {S.CLOSED},
    S.CLOSED: set(),
}


def assert_legal(current: S, target: S) -> None:
    if target not in _LEGAL.get(current, set()):
        raise IllegalTransition(current.value, target.value)


def legal_next_states(current: S) -> set[S]:
    return set(_LEGAL.get(current, set()))
