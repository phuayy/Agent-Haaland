import { useQuery } from "@tanstack/react-query";
import { getIncident } from "@/lib/api/incidents";
import { TERMINAL_STATUSES, type IncidentStatus } from "@/lib/api/types";
import { HaalandApiError } from "@/lib/api/client";

function isTerminal(status: IncidentStatus | undefined) {
  return !!status && (TERMINAL_STATUSES as string[]).includes(status);
}

export function useIncident(reference: string | undefined) {
  return useQuery({
    queryKey: ["incident", reference],
    queryFn: () => getIncident(reference as string),
    enabled: !!reference,
    refetchInterval: (query) => (isTerminal(query.state.data?.status) ? false : 5_000),
    retry: (failureCount, error) =>
      error instanceof HaalandApiError && error.status === 404 ? false : failureCount < 1,
  });
}
