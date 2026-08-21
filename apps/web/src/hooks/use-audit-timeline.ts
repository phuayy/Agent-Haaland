import { useQuery } from "@tanstack/react-query";
import { getAuditTimeline } from "@/lib/api/incidents";

export function useAuditTimeline(reference: string | undefined) {
  return useQuery({
    queryKey: ["audit-timeline", reference],
    queryFn: () => getAuditTimeline(reference as string),
    enabled: !!reference,
    refetchInterval: 5_000,
  });
}
