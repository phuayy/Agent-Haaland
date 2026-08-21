"""Canonical incident_events event types. Mirrors the table in
docs/03-data-model.md, extended with the debug-loop stages that docs/05
doesn't cover (code localisation, patch/check iteration, PR reviewers)."""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    ALERT_RECEIVED = "alert.received"
    ALERT_CORRELATED = "alert.correlated"
    INCIDENT_OPENED = "incident.opened"
    DEBUG_SESSION_SUBMITTED = "debug_session.submitted"
    EVIDENCE_COLLECTED = "evidence.collected"
    WORKSPACE_PREPARED = "workspace.prepared"
    PII_REDACTED = "pii.redacted"
    AI_CLASSIFIED = "ai.classified"
    CODE_LOCATED = "code.located"
    AI_EXPLORED = "ai.explored"
    AI_DIAGNOSED = "ai.diagnosed"
    AI_FIX_EVALUATED = "ai.fix_evaluated"
    AI_REMEDIATION_DRAFTED = "ai.remediation_drafted"
    AI_REFUSED = "ai.refused"
    AI_INVALID_OUTPUT = "ai.invalid_output"
    REMEDIATION_REJECTED_BY_POLICY = "ai.remediation_rejected_by_policy"
    PATCH_APPLIED = "patch.applied"
    CHECK_RAN = "check.ran"
    FIX_ATTEMPT_EXHAUSTED = "fix.attempts_exhausted"
    BRANCH_PUSHED = "branch.pushed"
    PR_OPENED = "pr.opened"
    NOTIFICATION_SENT = "notification.sent"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    APPROVAL_ESCALATED = "approval.escalated"
    PR_MERGED = "pr.merged"
    DEPLOY_COMPLETED = "deploy.completed"
    METRICS_RECOVERED = "metrics.recovered"
    TEST_GENERATED = "test.generated"
    TEST_VALIDATED = "test.validated"
    POSTMORTEM_GENERATED = "postmortem.generated"
    INCIDENT_CLOSED = "incident.closed"
    HUMAN_NOTE = "human.note"
    BUDGET_EXCEEDED = "budget.exceeded"
    RUN_FAILED = "run.failed"
