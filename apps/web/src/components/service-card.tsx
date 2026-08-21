"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, History } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HealthBadge } from "@/components/health-badge";
import { ServiceHistorySheet } from "@/components/service-history-sheet";
import type { Service } from "@/lib/api/types";
import { repoLabel, tierLabel, timeAgo } from "@/lib/format";

const TIER_VARIANT: Record<number, "default" | "secondary" | "outline"> = {
  1: "default",
  2: "secondary",
  3: "outline",
};

export function ServiceCard({ service }: { service: Service }) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const last = service.last_incident;

  return (
    <>
      <div className="group flex flex-col gap-4 rounded-xl border border-border bg-card p-5 shadow-sm transition-all hover:border-foreground/15 hover:shadow-md">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-medium leading-tight tracking-tight text-foreground">
              {service.name}
            </h3>
          </div>
          <Badge variant={TIER_VARIANT[service.tier] ?? "secondary"} className="shrink-0">
            {tierLabel(service.tier)}
          </Badge>
        </div>

        <div className="flex flex-1 flex-col gap-3">
          {service.repo_url ? (
            <a
              href={service.repo_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <span className="truncate font-mono">{repoLabel(service.repo_url)}</span>
              <ExternalLink className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
            </a>
          ) : (
            <p className="text-[13px] text-muted-foreground/70">No repository linked</p>
          )}

          <div className="flex items-center gap-2">
            <HealthBadge status={service.health} />
            {service.active_incident_count > 1 && (
              <span className="text-xs tabular-nums text-muted-foreground">
                {service.active_incident_count} open
              </span>
            )}
          </div>

          {last ? (
            <p className="text-xs text-muted-foreground">
              Last incident{" "}
              <Link
                href={`/incidents/${last.reference}`}
                className="font-mono tabular-nums text-foreground/75 hover:text-foreground hover:underline"
              >
                {last.reference}
              </Link>{" "}
              <span className="text-muted-foreground/70">&middot; {timeAgo(last.detected_at)}</span>
            </p>
          ) : (
            <p className="text-xs text-muted-foreground/70">No incidents yet</p>
          )}
        </div>

        <div className="flex items-center border-t border-border pt-3.5">
          <Button
            variant="ghost"
            size="sm"
            className="cursor-pointer rounded-md border border-slate-200 px-4 py-2 font-normal transition-colors hover:bg-slate-100"
            onClick={() => setHistoryOpen(true)}
          >
            <History className="h-3.5 w-3.5" />
            History
            {service.incident_count > 0 && (
              <span className="tabular-nums text-muted-foreground">({service.incident_count})</span>
            )}
          </Button>
        </div>
      </div>

      <ServiceHistorySheet service={service} open={historyOpen} onOpenChange={setHistoryOpen} />
    </>
  );
}
