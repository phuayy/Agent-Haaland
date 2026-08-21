import { apiGet, apiPost, apiUrl } from "./client";
import type {
  ApprovalRequest,
  AuditEvent,
  ChainVerification,
  DebugSessionAccepted,
  DebugSessionCreate,
  EvidenceItem,
  IncidentDetail,
  IncidentSummary,
  Postmortem,
  RejectionRequest,
  RemediationAttempt,
  ResumeResponse,
} from "./types";

export const createDebugSession = (body: DebugSessionCreate) =>
  apiPost<DebugSessionAccepted>("/api/debug-sessions", body);

export const listIncidents = () => apiGet<IncidentSummary[]>("/api/incidents");

export const getIncident = (reference: string) =>
  apiGet<IncidentDetail>(`/api/incidents/${encodeURIComponent(reference)}`);

export const approveIncident = (reference: string, body: ApprovalRequest) =>
  apiPost<ResumeResponse>(`/api/incidents/${encodeURIComponent(reference)}/approve`, body);

export const rejectIncident = (reference: string, body: RejectionRequest) =>
  apiPost<ResumeResponse>(`/api/incidents/${encodeURIComponent(reference)}/reject`, body);

export const getAuditTimeline = (reference: string) =>
  apiGet<AuditEvent[]>(`/api/incidents/${encodeURIComponent(reference)}/audit`);

export const verifyChain = (reference: string) =>
  apiGet<ChainVerification>(`/api/incidents/${encodeURIComponent(reference)}/audit/verify`);

export const getEvidence = (reference: string) =>
  apiGet<EvidenceItem[]>(`/api/incidents/${encodeURIComponent(reference)}/evidence`);

export const getRemediation = (reference: string) =>
  apiGet<RemediationAttempt[]>(`/api/incidents/${encodeURIComponent(reference)}/remediation`);

export const getPostmortem = (reference: string) =>
  apiGet<Postmortem>(`/api/incidents/${encodeURIComponent(reference)}/postmortem`);

export const postmortemMarkdownUrl = (reference: string) =>
  apiUrl(`/api/incidents/${encodeURIComponent(reference)}/postmortem`, { as_markdown: true });

export const githubBlobUrl = (repoFullName: string, ref: string, sourceRef: string): string | null => {
  const match = /^(.+):(\d+)-(\d+)$/.exec(sourceRef);
  if (!match) return null;
  const [, path, start, end] = match;
  return `https://github.com/${repoFullName}/blob/${ref}/${path}#L${start}-L${end}`;
};
