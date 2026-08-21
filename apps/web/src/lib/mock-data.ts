import { Service } from "./types";

// Seed services for the local address book — a starting point for a new
// browser profile, not backend data. Edit or delete freely; add real ones
// via "Add Service".
export const initialServices: Service[] = [
  {
    id: "svc-api-gateway",
    name: "API Gateway",
    repoUrl: "https://github.com/haaland-io/api-gateway",
    baseBranch: "main",
    ownerTeam: "Team Edge",
    tier: "Tier 1",
    incidentReferences: [],
  },
  {
    id: "svc-auth",
    name: "Auth Service",
    repoUrl: "https://github.com/haaland-io/auth-service",
    baseBranch: "main",
    ownerTeam: "Team Identity",
    tier: "Tier 1",
    incidentReferences: [],
  },
  {
    id: "svc-payments",
    name: "Payments Service",
    repoUrl: "https://github.com/haaland-io/payments-service",
    baseBranch: "main",
    ownerTeam: "Team Payments",
    tier: "Tier 1",
    incidentReferences: [],
  },
];
