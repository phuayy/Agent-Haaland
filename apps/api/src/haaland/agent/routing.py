"""Conditional edge functions. Kept separate from graph.py per docs/07 so
the routing logic — the part most worth unit testing without standing up
the whole graph — has no LangGraph import of its own beyond what the type
hints need."""

from __future__ import annotations

from haaland.agent.state import IncidentState

_LOW_SEVERITY = {"P3", "P4"}


def route_by_severity(state: IncidentState) -> str:
    classification = state.get("classification")
    if classification and classification.severity in _LOW_SEVERITY:
        return "low"
    return "high"


def route_by_diagnosis_confidence(state: IncidentState) -> str:
    diagnosis = state.get("diagnosis")
    if diagnosis is None:
        return "escalate"
    if diagnosis.confidence < 0.5 or diagnosis.recommended_strategy == "manual_investigation":
        return "escalate"
    return "confident"


def route_by_static_check(state: IncidentState, max_attempts: int) -> str:
    reports = state.get("check_reports") or []
    if reports and reports[-1]["outcome"] == "pass":
        return "pass"
    # The attempt ceiling must apply even when there is no report at all —
    # a policy-rejected draft (apply_patch wrote nothing, so static_check
    # had nothing to run) leaves `check_reports` empty, and without this
    # check that path would retry forever until the budget guard killed
    # the run with an exception instead of a clean escalation.
    if state.get("fix_attempt", 0) >= max_attempts:
        return "exhausted"
    return "retry"


def route_by_test_outcome(state: IncidentState, max_attempts: int) -> str:
    outcome = state.get("test_outcome")
    if outcome in ("accepted", "unrunnable"):
        return "proceed"
    if state.get("fix_attempt", 0) >= max_attempts:
        return "exhausted"
    return "retry"


def route_by_approval(state: IncidentState) -> str:
    approval = state.get("approval")
    if approval == "approved":
        return "approved"
    if approval == "rejected":
        return "rejected"
    return "escalated"
