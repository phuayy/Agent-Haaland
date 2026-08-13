"""The graph's typed state. Every node unpacks a slice of this and returns a
partial-dict patch — LangGraph merges patches into the checkpointed state,
which is what survives a worker restart (docs/02's durable-execution
requirement)."""

from __future__ import annotations

from typing import Literal, TypedDict
from uuid import UUID

from haaland.domain.models import (
    Classification,
    Diagnosis,
    EvidenceBundle,
    FixEvaluation,
    RedactionResult,
    RegressionTest,
    RemediationDraft,
)


class CheckReportDict(TypedDict):
    attempt: int
    outcome: str
    findings: list[dict]


class IncidentState(TypedDict, total=False):
    incident_id: UUID
    reference: str
    service_name: str
    repo_url: str
    repo_full_name: str
    base_ref: str
    log_text: str

    evidence: EvidenceBundle | None
    redaction: RedactionResult | None
    classification: Classification | None
    diagnosis: Diagnosis | None
    fix_evaluation: FixEvaluation | None
    remediation: RemediationDraft | None

    workspace_path: str | None
    base_sha: str | None
    changed_paths: list[str]
    combined_patch: str | None

    check_reports: list[CheckReportDict]
    fix_attempt: int
    last_failure_detail: str | None

    regression_test: RegressionTest | None
    test_validation_accepted: bool
    test_outcome: Literal["accepted", "failed", "unrunnable"] | None

    pr_number: int | None
    pr_url: str | None
    branch_name: str | None
    remediation_id: str | None

    approval: Literal["approved", "rejected", "escalated"] | None

    cost_usd: float
    errors: list[str]
