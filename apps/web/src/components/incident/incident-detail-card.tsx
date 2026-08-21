"use client";

import Link from "next/link";
import {
  AlertTriangle,
  GitBranch,
  Maximize2,
  Minimize2,
  ScrollText,
  Sparkles,
  Waypoints,
  Wrench,
} from "lucide-react";
import { SeverityBadge } from "@/components/severity-badge";
import { ApprovalPanel } from "@/components/incident/approval-panel";
import { AuditTimeline } from "@/components/incident/audit-timeline";
import { ChainIntegrityBanner } from "@/components/incident/chain-integrity-banner";
import { EvidenceLogs } from "@/components/incident/evidence-logs";
import { IncidentStepper } from "@/components/incident/incident-stepper";
import { IncidentTraceGraph } from "@/components/incident/incident-trace-graph";
import { PostmortemPanel } from "@/components/incident/postmortem-panel";
import { RemediationDiff } from "@/components/incident/remediation-diff";
import { Button } from "@/components/ui/button";
import { useIncident } from "@/hooks/use-incident";
import { HaalandApiError } from "@/lib/api/client";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

function Block({ icon, title, subtitle, children }: { icon?: React.ReactNode; title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <div className="flex items-center gap-1.5 text-[13px] font-semibold text-foreground">
          {icon}
          {title}
        </div>
        {subtitle && <span className="text-xs text-muted-foreground">{subtitle}</span>}
      </div>
      {children}
    </section>
  );
}

function ExpandToggle({ isExpanded, onToggle }: { isExpanded: boolean; onToggle?: () => void }) {
  if (!onToggle) return null;
  const label = isExpanded ? "Collapse detail view" : "Expand detail view";
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      onClick={onToggle}
      aria-label={label}
      aria-pressed={isExpanded}
      title={label}
      className="absolute top-4 right-4 z-10 text-muted-foreground hover:text-foreground"
    >
      {isExpanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
    </Button>
  );
}

export function IncidentDetailCard({
  reference,
  isExpanded = false,
  onToggleExpand,
}: {
  reference: string;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}) {
  const { data: incident, isPending, isError, error } = useIncident(reference);

  if (isPending) {
    return (
      <div className="relative flex flex-1 flex-col gap-4 p-6">
        <ExpandToggle isExpanded={isExpanded} onToggle={onToggleExpand} />
        <div className="h-6 w-56 animate-pulse rounded bg-muted" />
        <div className="h-8 w-full animate-pulse rounded bg-muted" />
        <div className="h-24 w-full animate-pulse rounded-lg bg-muted" />
        <div className="h-32 w-full animate-pulse rounded-lg bg-muted" />
      </div>
    );
  }

  const notFound = isError && error instanceof HaalandApiError && error.status === 404;

  if (notFound || !incident) {
    return (
      <div className="relative flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
        <ExpandToggle isExpanded={isExpanded} onToggle={onToggleExpand} />
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <AlertTriangle className="h-4.5 w-4.5" />
        </div>
        <p className="text-[15px] font-medium text-foreground">Incident {reference} not found</p>
        <Link href="/" className="text-sm text-primary hover:underline">
          Back to services
        </Link>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="relative flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
        <ExpandToggle isExpanded={isExpanded} onToggle={onToggleExpand} />
        <p className="text-[15px] font-medium text-foreground">Couldn&apos;t load {reference}</p>
        <p className="text-sm text-muted-foreground">{(error as Error).message}</p>
      </div>
    );
  }

  const isAwaitingApproval = incident.status === "awaiting_approval";

  return (
    <div className="flex h-full flex-col">
      <div
        className={cn(
          "relative flex flex-col gap-5 transition-all duration-300 ease-in-out",
          isExpanded ? "px-10 pt-8 pb-3" : "px-6 pt-6 pb-2",
        )}
      >
        <ExpandToggle isExpanded={isExpanded} onToggle={onToggleExpand} />
        <div className="flex flex-wrap items-start justify-between gap-3 pr-10">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[13px] font-semibold tabular-nums text-muted-foreground">
                {incident.reference}
              </span>
              <SeverityBadge severity={incident.severity} />
            </div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">{incident.title}</h2>
            <p className="text-xs text-muted-foreground">
              {incident.repo_full_name ?? "unknown repo"} &middot; detected {timeAgo(incident.detected_at)}
            </p>
          </div>
        </div>

        <IncidentStepper status={incident.status} />
      </div>

      <div
        className={cn(
          "flex-1 overflow-y-auto transition-all duration-300 ease-in-out",
          isExpanded ? "px-10 py-6" : "px-6 py-4",
        )}
      >
        <div className={cn("flex flex-col transition-all duration-300 ease-in-out", isExpanded ? "gap-8" : "gap-6")}>
          <ChainIntegrityBanner reference={reference} />

          {/* Above the root cause deliberately: the pane reads top-down as
              where it broke -> why it broke -> what was collected -> the fix. */}
          <Block
            icon={<Waypoints className="h-3.5 w-3.5 text-slate-600" />}
            title="Trace path"
            subtitle="The request's path from entry to failure"
          >
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <IncidentTraceGraph
                reference={reference}
                serviceName={incident.service_name}
                repoFullName={incident.repo_full_name}
                baseRef={incident.base_ref}
                status={incident.status}
                rootCauseSummary={incident.root_cause_summary}
              />
            </div>
          </Block>

          <Block icon={<Sparkles className="h-3.5 w-3.5 text-violet-600" />} title="AI root cause">
            <div
              className={cn(
                "rounded-lg border border-border bg-muted/60 transition-all duration-300 ease-in-out",
                isExpanded ? "p-6" : "p-4",
              )}
            >
              <p
                className={cn(
                  "text-foreground/90 transition-all duration-300 ease-in-out",
                  isExpanded ? "text-[15px] leading-8" : "text-[13.5px] leading-relaxed",
                )}
              >
                {incident.root_cause_summary ?? "Not diagnosed yet."}
              </p>
            </div>
          </Block>

          <Block
            icon={<ScrollText className="h-3.5 w-3.5 text-muted-foreground" />}
            title="Evidence"
            subtitle="What the agent collected before diagnosing"
          >
            <div
              className={cn("overflow-hidden transition-all duration-300 ease-in-out", isExpanded ? "h-80" : "h-64")}
            >
              <EvidenceLogs
                reference={reference}
                repoFullName={incident.repo_full_name}
                baseRef={incident.base_ref}
                expanded={isExpanded}
              />
            </div>
          </Block>

          <Block
            icon={<GitBranch className="h-3.5 w-3.5 text-muted-foreground" />}
            title="Remediation"
            subtitle="The drafted fix — review before approving"
          >
            <div className="h-72 overflow-hidden">
              <RemediationDiff reference={reference} />
            </div>
          </Block>

          <Block title="Audit timeline">
            <div className="rounded-lg border border-border bg-muted/60 p-4">
              <AuditTimeline reference={reference} />
            </div>
          </Block>

          <Block icon={<Wrench className="h-3.5 w-3.5 text-muted-foreground" />} title="Post-mortem">
            <div className="h-64 overflow-hidden">
              <PostmortemPanel reference={reference} />
            </div>
          </Block>
        </div>
      </div>

      {isAwaitingApproval && <ApprovalPanel reference={reference} />}
    </div>
  );
}
