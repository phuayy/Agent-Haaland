"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, History } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HealthBadge } from "@/components/health-badge";
import { ServiceHistorySheet } from "@/components/service-history-sheet";
import { TriggerDebugSessionDialog } from "@/components/incident/trigger-debug-session-dialog";
import { useIncident } from "@/hooks/use-incident";
import { Service } from "@/lib/types";
import { timeAgo } from "@/lib/format";

const TIER_VARIANT: Record<Service["tier"], "default" | "secondary" | "outline"> = {
  "Tier 1": "default",
  "Tier 2": "secondary",
  "Tier 3": "outline",
};

export function ServiceCard({ service }: { service: Service }) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const lastReference = service.incidentReferences[0];
  const { data: lastIncident } = useIncident(lastReference);

  const health =
    !lastIncident || lastIncident.severity === null
      ? "healthy"
      : lastIncident.severity === "P1"
        ? "p1"
        : "p2";

  return (
    <>
      <div className="group flex flex-col gap-4 rounded-xl border border-border bg-card p-5 shadow-sm transition-all hover:border-foreground/15 hover:shadow-md">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-medium leading-tight tracking-tight text-foreground">
              {service.name}
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{service.ownerTeam}</p>
          </div>
          <Badge variant={TIER_VARIANT[service.tier]} className="shrink-0">
            {service.tier}
          </Badge>
        </div>

        <div className="flex flex-1 flex-col gap-3">
          <a
            href={service.repoUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            <span className="truncate font-mono">{service.repoUrl.replace("https://", "")}</span>
            <ExternalLink className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
          </a>

          <div>
            <HealthBadge status={health} />
          </div>

          {lastIncident && (
            <p className="text-xs text-muted-foreground">
              Last triggered{" "}
              <Link
                href={`/incidents/${lastIncident.reference}`}
                className="font-mono tabular-nums text-foreground/75 hover:text-foreground hover:underline"
              >
                {lastIncident.reference}
              </Link>{" "}
              <span className="text-muted-foreground/70">&middot; {timeAgo(lastIncident.detected_at)}</span>
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 border-t border-border pt-3.5">
          <Button variant="ghost" size="sm" className="flex-1 font-normal" onClick={() => setHistoryOpen(true)}>
            <History className="h-3.5 w-3.5" />
            History
          </Button>
          <TriggerDebugSessionDialog service={service} />
        </div>
      </div>

      <ServiceHistorySheet service={service} open={historyOpen} onOpenChange={setHistoryOpen} />
    </>
  );
}
