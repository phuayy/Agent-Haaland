export type Tier = "Tier 1" | "Tier 2" | "Tier 3";

export type HealthStatus = "healthy" | "p1" | "p2";

export type Severity = "P1" | "P2";

export interface Service {
  id: string;
  name: string;
  repoUrl: string;
  baseBranch: string;
  ownerTeam: string;
  tier: Tier;
  health: HealthStatus;
  lastIncidentId?: string;
}

export interface AuditEvent {
  time: string;
  actor: string;
  action: string;
}

export interface GraphNode {
  id: string;
  label: string;
  failing: boolean;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
}

export interface Incident {
  id: string;
  serviceId: string;
  serviceName: string;
  severity: Severity;
  status: "active" | "resolved";
  title: string;
  createdAt: string;
  resolvedAt?: string;
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  logs: string;
  rootCause: string;
  remediation: string;
  auditTimeline: AuditEvent[];
}
