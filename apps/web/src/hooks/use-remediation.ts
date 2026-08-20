import { useQuery } from "@tanstack/react-query";
import { getRemediation } from "@/lib/api/incidents";

export function useRemediation(reference: string | undefined) {
  return useQuery({
    queryKey: ["remediation", reference],
    queryFn: () => getRemediation(reference as string),
    enabled: !!reference,
    refetchInterval: 5_000,
  });
}
