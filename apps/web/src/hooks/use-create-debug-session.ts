import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createDebugSession } from "@/lib/api/incidents";

export function useCreateDebugSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createDebugSession,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
