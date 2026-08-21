import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createService } from "@/lib/api/services";

export function useCreateService() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createService,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["services"] });
    },
  });
}
