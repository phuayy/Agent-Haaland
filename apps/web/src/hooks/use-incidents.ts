import { useQuery } from "@tanstack/react-query";
import { listIncidents } from "@/lib/api/incidents";

export function useIncidents() {
  return useQuery({
    queryKey: ["incidents"],
    queryFn: listIncidents,
    refetchInterval: 15_000,
  });
}
