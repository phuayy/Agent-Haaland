"""Pure domain models — no ORM, no framework. These are what services and the
LangGraph nodes pass around; db/models are the persistence shape of the same
concepts and are mapped to/from these at the repository boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from haaland.domain.enums import (
    ActorType,
    CheckOutcome,
    EvidenceKind,
    FileChangeAction,
    IncidentStatus,
    RemediationStrategy,
    Severity,
)


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class LogLine(BaseModel):
    timestamp: datetime
    level: str
    message: str
    attributes: dict[str, str] = Field(default_factory=dict)


class CodeLocation(BaseModel):
    """A candidate culprit location, ranked before the model ever sees it."""

    path: str
    start_line: int
    end_line: int
    snippet: str
    reason: str  # 'traceback_frame' | 'error_signature_grep' | 'symbol_reference'
    confidence: float = Field(ge=0, le=1)


class EvidenceItem(BaseModel):
    id: UUID | None = None
    kind: EvidenceKind
    source: str
    source_ref: str | None = None
    content: dict
    relevance: float = Field(default=0.5, ge=0, le=1)


class EvidenceBundle(BaseModel):
    incident_id: UUID
    service_name: str
    repo_full_name: str
    base_ref: str
    log_lines: list[LogLine] = Field(default_factory=list)
    code_candidates: list[CodeLocation] = Field(default_factory=list)
    deploy_context: list[dict] = Field(default_factory=list)


class RedactionResult(BaseModel):
    text: str
    vault_key: str
    entity_counts: dict[str, int] = Field(default_factory=dict)


class EvidenceRef(BaseModel):
    evidence_id: UUID | str
    excerpt: str = Field(max_length=500)
    why_relevant: str


class Classification(BaseModel):
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    customer_impact: Literal["none", "degraded", "partial_outage", "full_outage"]
    affected_services: list[str]
    blast_radius_estimate: str
    rationale: str = Field(max_length=1000)
    requires_immediate_page: bool


class Diagnosis(BaseModel):
    root_cause: str = Field(max_length=1500)
    category: Literal[
        "bad_deploy", "config_change", "resource_exhaustion", "downstream_dependency",
        "infrastructure", "data_issue", "external_provider", "logic_bug", "unknown",
    ]
    confidence: float = Field(ge=0, le=1)
    culprit_locations: list[CodeLocation] = Field(default_factory=list)
    supporting_evidence: list[EvidenceRef] = Field(min_length=1)
    contradicting_evidence: list[EvidenceRef] = Field(default_factory=list)
    recommended_strategy: RemediationStrategy
    strategy_rationale: str


class FixCandidate(BaseModel):
    summary: str
    approach: str
    risk: Literal["low", "medium", "high"]
    rationale: str


class FixEvaluation(BaseModel):
    candidates: list[FixCandidate] = Field(min_length=1, max_length=5)
    selected_index: int = Field(ge=0)
    selection_rationale: str


class FileChange(BaseModel):
    path: str
    action: FileChangeAction
    new_content: str
    change_summary: str


class RemediationDraft(BaseModel):
    strategy: RemediationStrategy
    pr_title: str = Field(max_length=100)
    pr_body_markdown: str
    files: list[FileChange] = Field(min_length=1, max_length=10)
    risk_assessment: str
    rollback_instructions: str
    verification_steps: list[str]


class CheckFinding(BaseModel):
    tool: Literal["ast", "ruff", "pytest"]
    outcome: CheckOutcome
    summary: str
    detail: str = ""


class CheckReport(BaseModel):
    attempt: int
    outcome: CheckOutcome
    findings: list[CheckFinding]


class RegressionTest(BaseModel):
    framework: Literal["pytest", "jest", "go-test"]
    file_path: str
    test_code: str
    test_name: str
    explanation: str
    setup_requirements: list[str] = Field(default_factory=list)


class TestValidation(BaseModel):
    fails_on_base: bool
    passes_on_fix: bool
    accepted: bool
    detail: str


class PostmortemProse(BaseModel):
    summary: str
    root_cause_narrative: str
    resolution_narrative: str
    went_well: str
    went_wrong: str
    action_items: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject", "request_changes"]
    actor: str
    reason: str | None = None
    channel: Literal["slack", "web", "api"] = "api"


class DebugSessionRequest(BaseModel):
    """The direct-input entrypoint contract: logs + repo, no alert required."""

    repo_url: str
    service_name: str
    log_text: str
    base_ref: str = "main"


class Incident(BaseModel):
    id: UUID
    reference: str
    title: str
    status: IncidentStatus
    severity: Severity | None = None
    severity_confidence: float | None = None
    repo_full_name: str | None = None
    detected_at: datetime
    root_cause_summary: str | None = None
    closed_reason: str | None = None


class IncidentEvent(BaseModel):
    id: int | None = None
    incident_id: UUID
    seq: int
    event_type: str
    actor_type: ActorType
    actor_id: str | None
    actor_label: str
    summary: str
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime
    prev_hash: bytes | None
    hash: bytes
