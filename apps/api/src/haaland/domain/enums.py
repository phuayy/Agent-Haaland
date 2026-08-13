"""Enumerations shared across the domain. Mirrors the Postgres ENUM types in
migrations/versions/0001_core_schema.py — keep the two in lockstep."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class IncidentStatus(StrEnum):
    DETECTED = "detected"
    ENRICHING = "enriching"
    TRIAGING = "triaging"
    TRIAGED_LOW = "triaged_low"
    DIAGNOSING = "diagnosing"
    AWAITING_APPROVAL = "awaiting_approval"
    ESCALATED = "escalated"
    APPROVED = "approved"
    REJECTED = "rejected"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    DOCUMENTING = "documenting"
    CLOSED = "closed"
    FAILED = "failed"


class ActorType(StrEnum):
    SYSTEM = "system"
    AI = "ai"
    HUMAN = "human"
    INTEGRATION = "integration"


class EvidenceKind(StrEnum):
    LOG = "log"
    TRACE = "trace"
    METRIC = "metric"
    DEPLOY = "deploy"
    CONFIG = "config"
    RUNBOOK = "runbook"
    SOURCE = "source"  # code excerpts pulled from the target repo — new for the debug loop


class RemediationStrategy(StrEnum):
    REVERT_DEPLOY = "revert_deploy"
    CONFIG_RESTORE = "config_restore"
    SCALE_RESOURCE = "scale_resource"
    DISABLE_FEATURE_FLAG = "disable_feature_flag"
    FAILOVER = "failover"
    CODE_FIX = "code_fix"  # new: patch generated + verified by the debug loop
    MANUAL_INVESTIGATION = "manual_investigation"


class RemediationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class FileChangeAction(StrEnum):
    MODIFY = "modify"
    REVERT = "revert"
    # Deliberately no DELETE, no EXECUTE — docs/09 layer 2 defence.


class CheckOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNRUNNABLE = "unrunnable"
