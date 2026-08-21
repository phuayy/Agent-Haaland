import { useQuery } from "@tanstack/react-query";
import { getEvidence } from "@/lib/api/incidents";

export function useEvidence(reference: string | undefined) {
  return useQuery({
    queryKey: ["evidence", reference],
    queryFn: () => getEvidence(reference as string),
    enabled: !!reference,
  });
}
