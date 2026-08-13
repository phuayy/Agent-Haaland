from __future__ import annotations

import pytest

from haaland.domain.enums import IncidentStatus as S
from haaland.domain.errors import IllegalTransition
from haaland.domain.state_machine import assert_legal


@pytest.mark.parametrize(
    "current,target",
    [
        (S.DETECTED, S.ENRICHING),
        (S.TRIAGING, S.DIAGNOSING),
        (S.TRIAGING, S.TRIAGED_LOW),
        (S.AWAITING_APPROVAL, S.APPROVED),
        (S.AWAITING_APPROVAL, S.REJECTED),
        (S.REJECTED, S.DIAGNOSING),
        (S.DOCUMENTING, S.CLOSED),
        (S.FAILED, S.CLOSED),
    ],
)
def test_legal_transitions_pass(current, target):
    assert_legal(current, target)  # must not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (S.DETECTED, S.CLOSED),          # can't skip straight to closed
        (S.CLOSED, S.DETECTED),          # closed is terminal
        (S.TRIAGED_LOW, S.DIAGNOSING),   # low-severity path doesn't diagnose
        (S.APPROVED, S.AWAITING_APPROVAL),  # can't go backwards
    ],
)
def test_illegal_transitions_raise(current, target):
    with pytest.raises(IllegalTransition):
        assert_legal(current, target)
