"""Conditional edge functions. Kept separate from graph.py per docs/07 so
the routing logic — the part most worth unit testing without standing up
the whole graph — has no LangGraph import of its own beyond what the type
hints need."""

from __future__ import annotations

from collections.abc import Collection

from haaland.agent.state import IncidentState


def route_by_severity(state: IncidentState, ticket_only: Collection[str] = ()) -> str:
    """Which bands get a ticket and nothing else.

    `ticket_only` is empty by default (settings.ticket_only_severity_set),
    so P1-P4 all run the full debug loop — clone, patch, branch, push, PR.
    The low-severity shortcut only exists for bands named explicitly."""
    classification = state.get("classification")
    if classification and ticket_only and classification.severity in ticket_only:
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
    # The attempt ceiling must apply even when there is no report at all
    # (static_check appends a failing entry for policy-rejected drafts, but
    # defend against an empty list anyway) — without this check that path
    # would retry forever until the budget guard killed the run with an
    # exception instead of a clean escalation.
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
