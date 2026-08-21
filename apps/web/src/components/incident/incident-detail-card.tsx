"use client";

import Link from "next/link";
import { AlertTriangle, GitBranch, ScrollText, Sparkles, Wrench } from "lucide-react";
import { SeverityBadge } from "@/components/severity-badge";
import { ApprovalPanel } from "@/components/incident/approval-panel";
import { AuditTimeline } from "@/components/incident/audit-timeline";
import { ChainIntegrityBanner } from "@/components/incident/chain-integrity-banner";
import { EvidenceLogs } from "@/components/incident/evidence-logs";
import { IncidentStepper } from "@/components/incident/incident-stepper";
import { PostmortemPanel } from "@/components/incident/postmortem-panel";
import { RemediationDiff } from "@/components/incident/remediation-diff";
import { useIncident } from "@/hooks/use-incident";
import { HaalandApiError } from "@/lib/api/client";
import { timeAgo } from "@/lib/format";

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

export function IncidentDetailCard({ reference }: { reference: string }) {
  const { data: incident, isPending, isError, error } = useIncident(reference);

  if (isPending) {
    return (
      <div className="flex flex-1 flex-col gap-4 p-6">
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
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
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
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
        <p className="text-[15px] font-medium text-foreground">Couldn&apos;t load {reference}</p>
        <p className="text-sm text-muted-foreground">{(error as Error).message}</p>
      </div>
    );
  }

  const isAwaitingApproval = incident.status === "awaiting_approval";

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-5 px-6 pt-6 pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
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

      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="flex flex-col gap-6">
          <ChainIntegrityBanner reference={reference} />

          <Block icon={<Sparkles className="h-3.5 w-3.5 text-violet-600" />} title="AI root cause">
            <div className="rounded-lg border border-border bg-muted/60 p-4">
              <p className="text-[13.5px] leading-relaxed text-foreground/90">
                {incident.root_cause_summary ?? "Not diagnosed yet."}
              </p>
            </div>
          </Block>

          <Block
            icon={<ScrollText className="h-3.5 w-3.5 text-muted-foreground" />}
            title="Evidence"
            subtitle="What the agent collected before diagnosing"
          >
            <div className="h-64 overflow-hidden">
              <EvidenceLogs reference={reference} repoFullName={incident.repo_full_name} baseRef={incident.base_ref} />
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
