import { cn } from "@/lib/utils";
import { IncidentStatus } from "@/lib/api/types";

// Collapses the 14-value backend status enum to 5 visual groups (docs/06's
// component inventory).
type Group = "detecting" | "analyzing" | "awaiting_approval" | "remediating" | "done";

const GROUP_OF: Record<IncidentStatus, Group> = {
  detected: "detecting",
  enriching: "detecting",
  triaging: "analyzing",
  diagnosing: "analyzing",
  awaiting_approval: "awaiting_approval",
  approved: "remediating",
  remediating: "remediating",
  verifying: "remediating",
  documenting: "remediating",
  triaged_low: "done",
  escalated: "done",
  rejected: "done",
  closed: "done",
  failed: "done",
};

const GROUP_CONFIG: Record<Group, { label: string; className: string }> = {
  detecting: { label: "Detecting", className: "bg-sky-50 text-sky-700 border-sky-200" },
  analyzing: { label: "Analyzing", className: "bg-violet-50 text-violet-700 border-violet-200" },
  awaiting_approval: {
    label: "Awaiting your approval",
    className: "bg-amber-50 text-amber-800 border-amber-300",
  },
  remediating: { label: "Remediating", className: "bg-sky-50 text-sky-700 border-sky-200" },
  done: { label: "", className: "" },
};

const DONE_LABEL: Partial<Record<IncidentStatus, { label: string; className: string }>> = {
  closed: { label: "Closed", className: "bg-emerald-50 text-emerald-600 border-emerald-200" },
  triaged_low: { label: "Triaged (low)", className: "bg-muted text-muted-foreground border-border" },
  rejected: { label: "Rejected", className: "bg-rose-50 text-rose-600 border-rose-200" },
  failed: { label: "Failed", className: "bg-rose-50 text-rose-600 border-rose-200" },
  escalated: { label: "Escalated", className: "bg-orange-50 text-orange-700 border-orange-200" },
};

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  const group = GROUP_OF[status];
  const config = group === "done" ? DONE_LABEL[status]! : GROUP_CONFIG[group];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-wide uppercase",
        config.className
      )}
    >
      {group === "awaiting_approval" && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" />
        </span>
      )}
      {config.label}
    </span>
  );
}
