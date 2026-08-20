import { useQuery } from "@tanstack/react-query";
import { verifyChain } from "@/lib/api/incidents";

export function useChainVerify(reference: string | undefined) {
  return useQuery({
    queryKey: ["chain-verify", reference],
    queryFn: () => verifyChain(reference as string),
    enabled: !!reference,
    staleTime: Infinity,
  });
}
