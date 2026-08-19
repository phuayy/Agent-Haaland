"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ChevronRight } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { useHaalandStore } from "@/lib/store";
import { Service } from "@/lib/types";
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
  const allIncidents = useHaalandStore((s) => s.incidents);
  const incidents = useMemo(
    () =>
      allIncidents
        .filter((i) => i.serviceId === service.id)
        .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()),
    [allIncidents, service.id]
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{service.name}</SheetTitle>
          <SheetDescription>Incident history for this service</SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-2 overflow-y-auto px-4 pb-4">
          {incidents.length === 0 && (
            <p className="text-sm text-muted-foreground">No incidents recorded.</p>
          )}
          {incidents.map((incident) => (
            <Link
              key={incident.id}
              href={`/incidents/${incident.id}`}
              onClick={() => onOpenChange(false)}
              className="flex items-center justify-between gap-3 rounded-lg border border-border p-3 text-sm hover:bg-secondary/50"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    {incident.id}
                  </span>
                  <Badge
                    variant={incident.status === "active" ? "destructive" : "secondary"}
                    className="h-4 px-1.5 text-[10px]"
                  >
                    {incident.status === "active" ? incident.severity : "Resolved"}
                  </Badge>
                </div>
                <p className="truncate text-sm">{incident.title}</p>
                <p className="text-xs text-muted-foreground">
                  {timeAgo(incident.createdAt)}
                </p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </Link>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
