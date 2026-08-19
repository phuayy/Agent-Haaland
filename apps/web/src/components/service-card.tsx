"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, History, Siren } from "lucide-react";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HealthBadge } from "@/components/health-badge";
import { ServiceHistorySheet } from "@/components/service-history-sheet";
import { useHaalandStore } from "@/lib/store";
import { Service } from "@/lib/types";
import { timeAgo } from "@/lib/format";

const TIER_VARIANT: Record<Service["tier"], "default" | "secondary" | "outline"> = {
  "Tier 1": "default",
  "Tier 2": "secondary",
  "Tier 3": "outline",
};

export function ServiceCard({ service }: { service: Service }) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const simulateIncident = useHaalandStore((s) => s.simulateIncident);
  const incidents = useHaalandStore((s) => s.incidents);

  const lastIncident = incidents.find((i) => i.id === service.lastIncidentId);

  function handleSimulate() {
    simulateIncident(service.id);
  }

  return (
    <>
      <Card className="flex flex-col gap-4 border-border/80 py-5">
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold leading-tight">{service.name}</h3>
            <p className="text-xs text-muted-foreground">{service.ownerTeam}</p>
          </div>
          <Badge variant={TIER_VARIANT[service.tier]}>{service.tier}</Badge>
        </CardHeader>

        <CardContent className="flex flex-1 flex-col gap-3">
          <a
            href={service.repoUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <span className="truncate">
              {service.repoUrl.replace("https://", "")}
            </span>
            <ExternalLink className="h-3.5 w-3.5 shrink-0" />
          </a>

          <div>
            <HealthBadge status={service.health} />
          </div>

          {lastIncident && (
            <p className="text-xs text-muted-foreground">
              Last Incident:{" "}
              <Link
                href={`/incidents/${lastIncident.id}`}
                className="font-mono tabular-nums text-foreground/80 hover:underline"
              >
                {lastIncident.id}
              </Link>{" "}
              &bull; {timeAgo(lastIncident.createdAt)}
            </p>
          )}
        </CardContent>

        <CardFooter className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="flex-1"
            onClick={() => setHistoryOpen(true)}
          >
            <History className="h-3.5 w-3.5" />
            View History
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1 border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={handleSimulate}
          >
            <Siren className="h-3.5 w-3.5" />
            Simulate Incident
          </Button>
        </CardFooter>
      </Card>

      <ServiceHistorySheet
        service={service}
        open={historyOpen}
        onOpenChange={setHistoryOpen}
      />
    </>
  );
}
