import { cn } from "@/lib/utils";
import { Severity } from "@/lib/api/types";

// P1 rose (the reserved incident-alert red), P2 orange, P3 amber, P4 slate —
// severity is the one place bright, saturated color is allowed; everything
// else in the UI stays neutral.
const SEVERITY_CONFIG: Record<Severity, string> = {
  P1: "bg-rose-50 text-rose-600 border-rose-200",
  P2: "bg-orange-50 text-orange-700 border-orange-200",
  P3: "bg-amber-50 text-amber-700 border-amber-200",
  P4: "bg-slate-100 text-slate-600 border-slate-200",
};

export function SeverityBadge({ severity }: { severity: Severity | null }) {
  if (!severity) {
    return (
      <span className="inline-flex items-center rounded-full border border-border bg-muted px-2.5 py-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
        Unclassified
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-wide uppercase",
        SEVERITY_CONFIG[severity]
      )}
    >
      {severity}
    </span>
  );
}
