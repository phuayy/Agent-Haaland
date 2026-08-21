// Local-only concepts. The backend has no services table/API at all (see
// docs/haaland-api-reference.md and the frontend-integration plan) — this is
// a client-side address book used to prefill and trigger real
// POST /api/debug-sessions calls, persisted to localStorage. Real incident
// data lives in React Query, driven by src/lib/api/types.ts, never here.

export type Tier = "Tier 1" | "Tier 2" | "Tier 3";

export type HealthStatus = "healthy" | "p1" | "p2";

export interface Service {
  id: string;
  name: string;
  repoUrl: string;
  baseBranch: string;
  ownerTeam: string;
  tier: Tier;
  /** References of debug sessions triggered from this card, most recent first. */
  incidentReferences: string[];
}
