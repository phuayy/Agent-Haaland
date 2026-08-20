import type { IncidentSummary } from "@/lib/api/types";

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

function medianMttrMinutes(incidents: IncidentSummary[]): number | null {
  const durations = incidents
    .filter((i) => i.closed_at)
    .map((i) => (new Date(i.closed_at as string).getTime() - new Date(i.detected_at).getTime()) / 60_000)
    .filter((m) => m >= 0)
    .sort((a, b) => a - b);
  if (durations.length === 0) return null;
  const mid = Math.floor(durations.length / 2);
  return durations.length % 2 === 0 ? (durations[mid - 1] + durations[mid]) / 2 : durations[mid];
}

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
  const mttr = medianMttrMinutes(incidents);

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
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
      <Kpi
        label="Median MTTR"
        value={mttr === null ? "—" : formatDuration(mttr)}
        hint={mttr === null ? "no closed incidents yet" : "detection to closure"}
        accent="border-t-violet-400"
      />
    </div>
  );
}
