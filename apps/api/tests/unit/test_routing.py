from __future__ import annotations

from haaland.agent import routing
from haaland.domain.models import Classification, Diagnosis


def _classification(severity: str) -> Classification:
    return Classification(
        severity=severity,
        confidence=0.8,
        customer_impact="degraded",
        affected_services=["orders-api"],
        blast_radius_estimate="single service",
        rationale="test",
        requires_immediate_page=False,
    )


def _diagnosis(confidence: float, strategy: str = "code_fix") -> Diagnosis:
    return Diagnosis(
        root_cause="division by zero",
        category="logic_bug",
        confidence=confidence,
        supporting_evidence=[{"evidence_id": "e1", "excerpt": "x", "why_relevant": "y"}],
        recommended_strategy=strategy,
        strategy_rationale="test",
    )


def test_route_by_severity_low():
    assert routing.route_by_severity({"classification": _classification("P4")}) == "low"
    assert routing.route_by_severity({"classification": _classification("P3")}) == "low"


def test_route_by_severity_high():
    assert routing.route_by_severity({"classification": _classification("P1")}) == "high"
    assert routing.route_by_severity({"classification": _classification("P2")}) == "high"


def test_route_by_diagnosis_confidence_low_escalates():
    assert routing.route_by_diagnosis_confidence({"diagnosis": _diagnosis(0.3)}) == "escalate"


def test_route_by_diagnosis_manual_investigation_escalates():
    state = {"diagnosis": _diagnosis(0.9, strategy="manual_investigation")}
    assert routing.route_by_diagnosis_confidence(state) == "escalate"


def test_route_by_diagnosis_confident_proceeds():
    assert routing.route_by_diagnosis_confidence({"diagnosis": _diagnosis(0.9)}) == "confident"


def test_route_by_static_check_pass():
    state = {"check_reports": [{"outcome": "pass"}], "fix_attempt": 1}
    assert routing.route_by_static_check(state, max_attempts=3) == "pass"


def test_route_by_static_check_retries_under_limit():
    state = {"check_reports": [{"outcome": "fail"}], "fix_attempt": 1}
    assert routing.route_by_static_check(state, max_attempts=3) == "retry"


def test_route_by_static_check_exhausted_at_limit():
    state = {"check_reports": [{"outcome": "fail"}], "fix_attempt": 3}
    assert routing.route_by_static_check(state, max_attempts=3) == "exhausted"


def test_route_by_test_outcome_proceeds_on_unrunnable():
    state = {"test_outcome": "unrunnable", "fix_attempt": 1}
    assert routing.route_by_test_outcome(state, max_attempts=3) == "proceed"


def test_route_by_approval_default_is_escalated():
    assert routing.route_by_approval({"approval": None}) == "escalated"
    assert routing.route_by_approval({}) == "escalated"
