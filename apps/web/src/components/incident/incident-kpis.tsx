import type { IncidentSummary } from "@/lib/api/types";

function Kpi({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint: string;
  accent: string;
}) {
  return (
    <div className={`rounded-xl border-x border-b border-border border-t-2 bg-card p-4 shadow-sm ${accent}`}>
      <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight text-foreground">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

export function IncidentKpis({ incidents }: { incidents: IncidentSummary[] }) {
  const terminal = new Set(["closed", "failed", "escalated", "triaged_low"]);
  const active = incidents.filter((i) => !terminal.has(i.status)).length;
  const awaitingApproval = incidents.filter((i) => i.status === "awaiting_approval").length;
  const closed = incidents.filter((i) => i.status === "closed").length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-3">
      <Kpi
        label="Active incidents"
        value={String(active)}
        hint={`of ${incidents.length} in the last 50`}
        accent="border-t-sky-400"
      />
      <Kpi
        label="Awaiting approval"
        value={String(awaitingApproval)}
        hint="need a decision now"
        accent="border-t-amber-400"
      />
      <Kpi
        label="Closed"
        value={String(closed)}
        hint="fully resolved"
        accent="border-t-emerald-400"
      />
    </div>
  );
}
