import { useMutation, useQueryClient } from "@tanstack/react-query";
import { approveIncident, rejectIncident } from "@/lib/api/incidents";
import type { ApprovalRequest, RejectionRequest } from "@/lib/api/types";

export function useApproveIncident(reference: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ApprovalRequest) => approveIncident(reference, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incident", reference] });
      qc.invalidateQueries({ queryKey: ["audit-timeline", reference] });
    },
  });
}

export function useRejectIncident(reference: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RejectionRequest) => rejectIncident(reference, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incident", reference] });
      qc.invalidateQueries({ queryKey: ["audit-timeline", reference] });
    },
  });
}
