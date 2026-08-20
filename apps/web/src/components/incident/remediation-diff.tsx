"use client";

import { ExternalLink, GitPullRequest, Loader2 } from "lucide-react";
import { useRemediation } from "@/hooks/use-remediation";

const STRATEGY_LABEL: Record<string, string> = {
  revert_deploy: "Revert deploy",
  config_restore: "Restore configuration",
  scale_resource: "Scale resource",
  disable_feature_flag: "Disable feature flag",
  failover: "Failover",
  code_fix: "Code fix",
  manual_investigation: "Manual investigation",
};

function colorizeDiffLine(line: string, key: number) {
  let className = "text-muted-foreground";
  if (line.startsWith("+++") || line.startsWith("---")) className = "text-foreground font-medium";
  else if (line.startsWith("@@")) className = "text-violet-700";
  else if (line.startsWith("+")) className = "text-emerald-700 bg-emerald-100";
  else if (line.startsWith("-")) className = "text-red-700 bg-red-100";
  else if (line.startsWith("diff --git")) className = "text-sky-700 font-medium";

  return (
    <div key={key} className={className}>
      {line || " "}
    </div>
  );
}

export function RemediationDiff({ reference }: { reference: string }) {
  const { data, isPending, isError } = useRemediation(reference);

  if (isPending) {
    return (
      <div className="flex items-center gap-2 p-4 text-[13px] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Loading remediation…
      </div>
    );
  }

  if (isError) {
    return <p className="p-4 text-[13px] text-muted-foreground">Could not load the remediation.</p>;
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
        <GitPullRequest className="h-4 w-4 text-muted-foreground/60" />
        <p className="text-[13px] text-muted-foreground">
          No remediation drafted yet — this appears once the agent has diagnosed the root cause.
        </p>
      </div>
    );
  }

  const latest = data[data.length - 1];

  return (
    <div className="flex h-full flex-col gap-3 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium text-foreground/90 shadow-sm">
            {STRATEGY_LABEL[latest.strategy] ?? latest.strategy}
          </span>
          {data.length > 1 && (
            <span className="text-xs tabular-nums text-muted-foreground">attempt {latest.attempt_count}</span>
          )}
        </div>
        {latest.pr_url && (
          <a
            href={latest.pr_url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-xs text-sky-700 hover:underline"
          >
            <GitPullRequest className="h-3.5 w-3.5" />
            View PR{latest.pr_number ? ` #${latest.pr_number}` : ""}
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      <p className="text-[13.5px] leading-relaxed text-foreground/90">{latest.rationale}</p>

      {latest.risk_notes && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800">
          {latest.risk_notes}
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-muted/60 p-3 font-mono text-[11px] leading-relaxed whitespace-pre">
        {latest.patch.split("\n").map((line, i) => colorizeDiffLine(line, i))}
      </div>
    </div>
  );
}
