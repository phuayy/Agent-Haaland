"use client";

import { AlertTriangle, ShieldCheck } from "lucide-react";
import { SeverityBadge } from "@/components/severity-badge";
import { IncidentStatusBadge } from "@/components/incident-status-badge";
import { timeAgo } from "@/lib/format";
import type { IncidentSummary } from "@/lib/api/types";

function ListSkeleton() {
  return (
    <div className="flex flex-col divide-y divide-border">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex animate-pulse items-center gap-3 px-4 py-3.5">
          <div className="h-5 w-11 rounded-full bg-muted" />
          <div className="flex-1 space-y-1.5">
            <div className="h-2.5 w-24 rounded bg-muted" />
            <div className="h-3 w-40 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function IncidentMasterList({
  incidents,
  isPending,
  isError,
  selected,
  onSelect,
}: {
  incidents: IncidentSummary[] | undefined;
  isPending: boolean;
  isError: boolean;
  selected: string | undefined;
  onSelect: (reference: string) => void;
}) {
  if (isPending) return <ListSkeleton />;

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-16 text-center">
        <AlertTriangle className="h-4 w-4 text-muted-foreground" />
        <p className="text-[13px] text-muted-foreground">Couldn&apos;t reach the backend.</p>
      </div>
    );
  }

  if (!incidents || incidents.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-16 text-center">
        <ShieldCheck className="h-5 w-5 text-emerald-500" />
        <p className="text-[13px] font-medium text-foreground">All clear</p>
        <p className="text-xs text-muted-foreground">No incidents recorded.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col divide-y divide-border">
      {incidents.map((incident) => {
        const isSelected = incident.reference === selected;
        return (
          <button
            key={incident.reference}
            type="button"
            onClick={() => onSelect(incident.reference)}
            className={`flex w-full items-start gap-3 border-l-[3px] px-4 py-3.5 text-left transition-colors ${
              isSelected
                ? "border-l-emerald-600 bg-emerald-50"
                : "border-l-transparent hover:bg-muted/60"
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {incident.reference}
                </span>
                <SeverityBadge severity={incident.severity} />
              </div>
              <p className="mt-1 truncate text-[13.5px] font-medium text-foreground">{incident.title}</p>
              <div className="mt-1.5 flex items-center gap-2">
                <IncidentStatusBadge status={incident.status} />
                <span className="text-[11px] text-muted-foreground">{timeAgo(incident.detected_at)}</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
