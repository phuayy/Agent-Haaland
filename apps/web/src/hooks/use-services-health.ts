import { useQueries } from "@tanstack/react-query";
import { getIncident } from "@/lib/api/incidents";
import type { HealthStatus, Service } from "@/lib/types";

function deriveHealth(severity: string | null | undefined): HealthStatus {
  if (severity === "P1") return "p1";
  if (severity === "P2" || severity === "P3" || severity === "P4") return "p2";
  return "healthy";
}

/** Polls each service's most recent triggered incident and derives a health
 * pill from its live severity. `useQueries` (not a loop of `useQuery`) so the
 * hook stays valid as services are added/removed. */
export function useServicesHealth(services: Service[]) {
  const results = useQueries({
    queries: services.map((s) => {
      const reference = s.incidentReferences[0];
      return {
        queryKey: ["incident", reference],
        queryFn: () => getIncident(reference as string),
        enabled: !!reference,
        refetchInterval: 5_000,
      };
    }),
  });

  const healthById = new Map<string, HealthStatus>();
  services.forEach((s, i) => {
    const data = results[i]?.data;
    healthById.set(s.id, s.incidentReferences.length === 0 ? "healthy" : deriveHealth(data?.severity));
  });

  return healthById;
}
