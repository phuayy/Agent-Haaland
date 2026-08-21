import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createDebugSession } from "@/lib/api/incidents";

export function useCreateDebugSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createDebugSession,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incidents"] });
      // The new incident is linked to its service server-side, so the
      // registry's health pills and history counts are stale the moment this
      // returns.
      qc.invalidateQueries({ queryKey: ["services"] });
      qc.invalidateQueries({ queryKey: ["service-incidents"] });
    },
  });
}
