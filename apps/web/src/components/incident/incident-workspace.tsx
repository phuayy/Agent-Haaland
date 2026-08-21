"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { IncidentKpis } from "@/components/incident/incident-kpis";
import { IncidentMasterList } from "@/components/incident/incident-master-list";
import { IncidentDetailCard } from "@/components/incident/incident-detail-card";
import { useIncidents } from "@/hooks/use-incidents";
import { cn } from "@/lib/utils";

export function IncidentWorkspace({ initialReference }: { initialReference?: string }) {
  const { data: incidents, isPending, isError } = useIncidents();
  const [explicitSelection, setExplicitSelection] = useState<string | undefined>(initialReference);
  const [isExpanded, setIsExpanded] = useState(false);
  const router = useRouter();

  // No effect needed: fall back to the newest incident once the list loads,
  // computed at render time rather than synced via setState-in-effect.
  const selected = explicitSelection ?? incidents?.[0]?.reference;

  function handleSelect(reference: string) {
    setExplicitSelection(reference);
    router.replace(`/incidents/${reference}`, { scroll: false });
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 px-8 py-7">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Incident Operations
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Incidents</h1>
          <p className="text-sm text-muted-foreground">Decision performance and live incident activity.</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
          Live data
        </div>
      </div>

      {/* Collapsed away in expanded mode. The negative margin swallows the
          parent flex gap so the detail card gains the full vertical band. */}
      <div
        aria-hidden={isExpanded}
        className={cn(
          "overflow-hidden transition-all duration-300 ease-in-out",
          isExpanded ? "pointer-events-none -mb-6 max-h-0 opacity-0" : "max-h-56 opacity-100",
        )}
      >
        <IncidentKpis incidents={incidents ?? []} />
      </div>

      <div
        className={cn(
          "grid min-h-0 flex-1 grid-cols-1 transition-all duration-300 ease-in-out",
          isExpanded ? "gap-0 lg:grid-cols-[0px_1fr]" : "gap-5 lg:grid-cols-[380px_1fr]",
        )}
      >
        <div
          aria-hidden={isExpanded}
          className={cn(
            "min-h-0 overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-300 ease-in-out",
            isExpanded
              ? "pointer-events-none h-0 border-transparent opacity-0 shadow-none lg:h-auto"
              : "border-border opacity-100",
          )}
        >
          <div className="overflow-y-auto" style={{ maxHeight: "calc(100vh - 260px)" }}>
            <IncidentMasterList
              incidents={incidents}
              isPending={isPending}
              isError={isError}
              selected={selected}
              onSelect={handleSelect}
            />
          </div>
        </div>

        <div className="min-h-0 overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all duration-300 ease-in-out">
          {selected ? (
            <IncidentDetailCard
              reference={selected}
              isExpanded={isExpanded}
              onToggleExpand={() => setIsExpanded((prev) => !prev)}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Select an incident to view details.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
