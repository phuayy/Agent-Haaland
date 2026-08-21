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
import { useIncident } from "@/hooks/use-incident";
import { Service } from "@/lib/types";
import { timeAgo } from "@/lib/format";

function HistoryRow({ reference, onNavigate }: { reference: string; onNavigate: () => void }) {
  const { data, isPending } = useIncident(reference);

  if (isPending || !data) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 p-3 text-sm text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        <span className="font-mono text-xs tabular-nums">{reference}</span>
      </div>
    );
  }

  return (
    <Link
      href={`/incidents/${reference}`}
      onClick={onNavigate}
      className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3 text-sm shadow-sm transition-all hover:border-foreground/15 hover:shadow-md"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tabular-nums text-muted-foreground">{reference}</span>
          <IncidentStatusBadge status={data.status} />
        </div>
        <p className="truncate text-[13.5px] text-foreground/90">{data.title}</p>
        <p className="text-xs text-muted-foreground">{timeAgo(data.detected_at)}</p>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </Link>
  );
}

export function ServiceHistorySheet({
  service,
  open,
  onOpenChange,
}: {
  service: Service;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{service.name}</SheetTitle>
          <SheetDescription>Debug sessions triggered from this card</SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-2 overflow-y-auto px-4 pb-4">
          {service.incidentReferences.length === 0 && (
            <p className="text-sm text-muted-foreground">No incidents triggered yet.</p>
          )}
          {service.incidentReferences.map((reference) => (
            <HistoryRow key={reference} reference={reference} onNavigate={() => onOpenChange(false)} />
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
