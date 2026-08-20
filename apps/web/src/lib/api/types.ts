// Hand-written to mirror apps/api exactly — see docs/haaland-api-reference.md.
// No codegen: several backend routes return a bare dict/list[dict] with no
// response_model, so OpenAPI codegen wouldn't produce useful types for them.

export type Severity = "P1" | "P2" | "P3" | "P4";

export type IncidentStatus =
  | "detected"
  | "enriching"
  | "triaging"
  | "triaged_low"
  | "diagnosing"
  | "awaiting_approval"
  | "escalated"
  | "approved"
  | "rejected"
  | "remediating"
  | "verifying"
  | "documenting"
  | "closed"
  | "failed";

export const TERMINAL_STATUSES: readonly IncidentStatus[] = [
  "closed",
  "failed",
  "escalated",
  "triaged_low",
];

export type ActorType = "system" | "ai" | "human" | "integration";

export interface IncidentSummary {
  reference: string;
  title: string;
  status: IncidentStatus;
  severity: Severity | null;
  detected_at: string;
  closed_at: string | null;
}

export interface IncidentDetail {
  reference: string;
  title: string;
  status: IncidentStatus;
  severity: Severity | null;
  severity_confidence: number | null;
  repo_full_name: string | null;
  base_ref: string | null;
  root_cause_summary: string | null;
  detected_at: string;
  closed_at: string | null;
}

export interface DebugSessionCreate {
  repo_url: string;
  service_name: string;
  log_text: string;
  base_ref?: string;
}

export interface DebugSessionAccepted {
  reference: string;
  incident_id: string;
  status: string;
}

export interface AuditEvent {
  seq: number;
  event_type: string;
  actor_type: ActorType;
  actor_label: string;
  summary: string;
  occurred_at: string;
}

export interface ChainVerification {
  valid: boolean;
  events_checked: number;
  first_divergence_seq: number | null;
}

export type EvidenceKind =
  | "log"
  | "trace"
  | "metric"
  | "deploy"
  | "config"
  | "runbook"
  | "source";

export interface EvidenceLogContent {
  line_count: number;
}

export interface EvidenceSourceContent {
  reason: string;
  confidence: number;
}

export interface EvidenceItem {
  kind: EvidenceKind;
  source: string;
  source_ref: string | null;
  content: EvidenceLogContent | EvidenceSourceContent | Record<string, unknown>;
  relevance: number | null;
  collected_at: string;
}

export type RemediationStrategy =
  | "revert_deploy"
  | "config_restore"
  | "scale_resource"
  | "disable_feature_flag"
  | "failover"
  | "code_fix"
  | "manual_investigation";

export type RemediationStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "merged"
  | "superseded"
  | "expired";

export interface RemediationAttempt {
  strategy: RemediationStrategy;
  rationale: string;
  risk_notes: string | null;
  repo_full_name: string;
  branch_name: string;
  base_sha: string;
  patch: string;
  attempt_count: number;
  pr_number: number | null;
  pr_url: string | null;
  status: RemediationStatus;
  created_at: string;
  resolved_at: string | null;
}

export interface Postmortem {
  version: number;
  markdown: string;
  generated_at: string;
}

export interface ApprovalRequest {
  actor: string;
  reason?: string | null;
}

export interface RejectionRequest {
  actor: string;
  reason: string;
}

export interface ResumeResponse {
  status: string;
}

export interface NotificationChannels {
  channels: string[];
  lark_mode: string;
  lark_domain: string;
}

export interface LarkVerifyResult {
  app_id: string;
  base_url: string;
  token_expires_in_seconds: number;
}

export interface LarkChat {
  chat_id: string | null;
  name: string | null;
  description: string | null;
}

export interface LarkChatsResult {
  chats: LarkChat[];
  count: number;
}

export interface NotificationTestDelivery {
  channel: string;
  status: "sent" | "failed";
  external_ref: string | null;
  detail: string | null;
}

export type NotificationTestResult =
  | { results: NotificationTestDelivery[] }
  | { channels: []; detail: string };
