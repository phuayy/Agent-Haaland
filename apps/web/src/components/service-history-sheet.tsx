"use client";

import Link from "next/link";
import { ChevronRight, Loader2 } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { IncidentStatusBadge } from "@/components/incident-status-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { useServiceIncidents } from "@/hooks/use-service-incidents";
import type { Service } from "@/lib/api/types";
import { timeAgo } from "@/lib/format";

export function ServiceHistorySheet({
  service,
  open,
  onOpenChange,
}: {
  service: Service;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  // One request for the whole history — the backend joins incidents to the
  // service, so this shows sessions triggered from anywhere, not only the
  // ones this browser started.
  const { data, isPending, isError, error } = useServiceIncidents(service.id, open);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{service.name}</SheetTitle>
          <SheetDescription>Incidents opened against this service</SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-2 overflow-y-auto px-4 pb-4">
          {isPending && (
            <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading history…
            </div>
          )}

          {isError && (
            <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              {error.message}
            </p>
          )}

          {data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No incidents triggered yet.</p>
          )}

          {data?.map((incident) => (
            <Link
              key={incident.reference}
              href={`/incidents/${incident.reference}`}
              onClick={() => onOpenChange(false)}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3 text-sm shadow-sm transition-all hover:border-foreground/15 hover:shadow-md"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    {incident.reference}
                  </span>
                  <IncidentStatusBadge status={incident.status} />
                  <SeverityBadge severity={incident.severity} />
                </div>
                <p className="truncate text-[13.5px] text-foreground/90">{incident.title}</p>
                <p className="text-xs text-muted-foreground">{timeAgo(incident.detected_at)}</p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </Link>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
