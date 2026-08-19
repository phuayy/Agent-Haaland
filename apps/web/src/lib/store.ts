import { create } from "zustand";
import { initialIncidents, initialServices } from "./mock-data";
import { Incident, Service, Severity, Tier } from "./types";

let incidentCounter = 43;

const SIMULATED_ROOT_CAUSES = [
  {
    title: "Memory leak in request handler causing pod OOMKills",
    rootCause:
      "A recently deployed caching layer retains references to full request payloads instead of digests, causing heap growth of ~40MB/min under sustained traffic until pods hit their memory limit and are OOMKilled.",
    remediation:
      "Rolled back the caching layer change and patched the cache key to store a SHA-256 digest instead of the full payload. Added a memory-growth alert at 70% of pod limit.",
  },
  {
    title: "Upstream dependency timeout cascading into circuit breaker trips",
    rootCause:
      "A downstream service began responding with p99 latency of 6.2s (up from 180ms baseline), exceeding the configured 2s timeout and tripping the circuit breaker for all callers.",
    remediation:
      "Increased timeout budget to 3s with a fallback to cached data, and paged the owning team for the downstream regression.",
  },
  {
    title: "Bad configuration rollout disabled health check endpoint",
    rootCause:
      "A configuration change intended for staging was promoted to production, disabling the /healthz endpoint and causing the load balancer to mark all instances unhealthy.",
    remediation:
      "Reverted the configuration change and added an environment-scoped guard to the deploy pipeline to prevent staging configs from reaching production.",
  },
];

function randomFrom<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function buildSimulatedIncident(service: Service): Incident {
  incidentCounter += 1;
  const id = `INC-2026-${String(incidentCounter).padStart(4, "0")}`;
  const severity: Severity = Math.random() > 0.5 ? "P1" : "P2";
  const scenario = randomFrom(SIMULATED_ROOT_CAUSES);
  const now = new Date().toISOString();

  return {
    id,
    serviceId: service.id,
    serviceName: service.name,
    severity,
    status: "active",
    title: scenario.title,
    createdAt: now,
    graphNodes: [
      { id: "client", label: "Client / CDN", failing: false },
      { id: service.id, label: service.name, failing: true },
      { id: "db", label: "Postgres Primary", failing: false },
    ],
    graphEdges: [
      { id: "e1", source: "client", target: service.id },
      { id: "e2", source: service.id, target: "db" },
    ],
    logs: `File "/app/haaland/${service.id.replace("svc-", "")}/routes/handler.py", line 52, in handle_request
    result = await process(request)
fastapi.exceptions.HTTPException: 500 Internal Server Error

WARNING  haaland.${service.id.replace("svc-", "")}  anomalous error rate detected
ERROR    haaland.${service.id.replace("svc-", "")}  ${scenario.title.toLowerCase()}
CRITICAL haaland.${service.id.replace("svc-", "")}.health  readiness probe failing`,
    rootCause: scenario.rootCause,
    remediation: scenario.remediation,
    auditTimeline: [
      { time: new Date().toLocaleTimeString(), actor: "agent-haaland", action: `Anomaly detected on ${service.name}` },
      { time: new Date().toLocaleTimeString(), actor: "agent-haaland", action: "Pulled traceback and correlated recent deploys" },
      { time: new Date().toLocaleTimeString(), actor: "agent-haaland", action: "Root cause hypothesis formed" },
      { time: new Date().toLocaleTimeString(), actor: "agent-haaland", action: "Drafted remediation plan for review" },
    ],
  };
}

interface HaalandStore {
  services: Service[];
  incidents: Incident[];
  addService: (input: {
    name: string;
    repoUrl: string;
    baseBranch: string;
    tier: Tier;
    ownerTeam: string;
  }) => void;
  simulateIncident: (serviceId: string) => Incident;
}

export const useHaalandStore = create<HaalandStore>((set, get) => ({
  services: initialServices,
  incidents: initialIncidents,

  addService: (input) =>
    set((state) => ({
      services: [
        ...state.services,
        {
          id: `svc-${input.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Date.now().toString(36)}`,
          name: input.name,
          repoUrl: input.repoUrl,
          baseBranch: input.baseBranch || "main",
          ownerTeam: input.ownerTeam,
          tier: input.tier,
          health: "healthy",
        },
      ],
    })),

  simulateIncident: (serviceId) => {
    const service = get().services.find((s) => s.id === serviceId);
    if (!service) throw new Error("Service not found");
    const incident = buildSimulatedIncident(service);
    set((state) => ({
      incidents: [incident, ...state.incidents],
      services: state.services.map((s) =>
        s.id === serviceId
          ? { ...s, health: incident.severity === "P1" ? "p1" : "p2", lastIncidentId: incident.id }
          : s
      ),
    }));
    return incident;
  },
}));
