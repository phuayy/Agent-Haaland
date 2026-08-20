import { useQuery } from "@tanstack/react-query";
import { getPostmortem } from "@/lib/api/incidents";
import { HaalandApiError } from "@/lib/api/client";
import type { Postmortem } from "@/lib/api/types";

export function usePostmortem(reference: string | undefined) {
  return useQuery<Postmortem | null>({
    queryKey: ["postmortem", reference],
    queryFn: async () => {
      try {
        return await getPostmortem(reference as string);
      } catch (err) {
        // "incident not found" (bad reference) is a real error; "postmortem
        // not yet generated" (valid incident, not documented yet) is not —
        // both are 404s, distinguished only by message text (see the API
        // reference doc's Postmortems section).
        if (err instanceof HaalandApiError && err.status === 404 && err.message.includes("not yet generated")) {
          return null;
        }
        throw err;
      }
    },
    enabled: !!reference,
  });
}
