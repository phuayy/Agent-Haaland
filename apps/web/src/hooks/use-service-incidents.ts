import { useQuery } from "@tanstack/react-query";
import { listServiceIncidents } from "@/lib/api/services";

/** Every incident ever opened against a service, newest first — the backend
 * join, not a list of references the browser remembers triggering. `enabled`
 * keeps the request from firing until the history sheet is actually open. */
export function useServiceIncidents(serviceId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["service-incidents", serviceId],
    queryFn: () => listServiceIncidents(serviceId as string),
    enabled: !!serviceId && enabled,
    refetchInterval: 10_000,
  });
}
