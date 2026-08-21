import { useQuery } from "@tanstack/react-query";
import { listServices } from "@/lib/api/services";

/** The registry itself, polled. Health and the last-incident line on each
 * card are computed server-side from live incident rows, so a debug session
 * triggered anywhere — this tab, another browser, a curl — turns the card red
 * within one interval. Kept slower than the 5s incident poll: the registry
 * changes on the scale of runs, not of graph nodes. */
export function useServices() {
  return useQuery({
    queryKey: ["services"],
    queryFn: listServices,
    refetchInterval: 10_000,
  });
}
