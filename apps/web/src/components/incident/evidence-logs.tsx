"use client";

import { ExternalLink, FileSearch, Loader2, ScrollText } from "lucide-react";
import { useEvidence } from "@/hooks/use-evidence";
import { githubBlobUrl } from "@/lib/api/incidents";
import { cn } from "@/lib/utils";
import type { EvidenceItem, EvidenceLogContent, EvidenceSourceContent } from "@/lib/api/types";

function isSourceContent(content: EvidenceItem["content"]): content is EvidenceSourceContent {
  return "reason" in content && "confidence" in content;
}

function isLogContent(content: EvidenceItem["content"]): content is EvidenceLogContent {
  return "line_count" in content;
}

const REASON_LABEL: Record<string, string> = {
  traceback_frame: "traceback frame",
  function_name_grep: "function name match",
  error_signature_grep: "error signature match",
};

function reasonLabel(reason: string): string {
  return REASON_LABEL[reason] ?? reason;
}

export function EvidenceLogs({
  reference,
  repoFullName,
  baseRef,
  expanded = false,
}: {
  reference: string;
  repoFullName: string | null;
  baseRef: string | null;
  /** Roomier padding and line-heights when the detail card is expanded. */
  expanded?: boolean;
}) {
  const { data, isPending, isError } = useEvidence(reference);

  if (isPending) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-[13px] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Loading evidence…
      </div>
    );
  }

  if (isError) {
    return <p className="p-4 text-[13px] text-muted-foreground">Could not load evidence.</p>;
  }

  const logRow = data?.find((e) => e.kind === "log" && isLogContent(e.content));
  const candidates = (data ?? [])
    .filter((e) => e.kind === "source" && isSourceContent(e.content))
    .sort((a, b) => (b.relevance ?? 0) - (a.relevance ?? 0));

  if (!data || data.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
        <ScrollText className="h-4 w-4 text-muted-foreground/60" />
        <p className="text-[13px] text-muted-foreground">
          No evidence collected yet — this appears once the incident starts enriching.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-border bg-muted/60">
      <div className="flex items-center gap-2 border-b border-border bg-muted px-3 py-2">
        <ScrollText className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">Candidate locations</span>
      </div>

      <div className={cn("flex-1 overflow-auto transition-all duration-300 ease-in-out", expanded ? "p-5" : "p-3")}>
        {logRow && isLogContent(logRow.content) && (
          <p className="mb-3 text-xs text-muted-foreground">
            {logRow.content.line_count} log line{logRow.content.line_count === 1 ? "" : "s"} ingested.
          </p>
        )}

        {candidates.length === 0 && (
          <p className="text-xs text-muted-foreground">No candidate code locations were located.</p>
        )}

        <ol className={cn("flex flex-col transition-all duration-300 ease-in-out", expanded ? "gap-3" : "gap-2")}>
          {candidates.map((c, i) => {
            const content = c.content as EvidenceSourceContent;
            const link =
              repoFullName && baseRef && c.source_ref
                ? githubBlobUrl(repoFullName, baseRef, c.source_ref)
                : null;
            const confidencePct = Math.round(content.confidence * 100);
            return (
              <li
                key={i}
                className={cn(
                  "rounded-md border border-border bg-card shadow-sm transition-all duration-300 ease-in-out",
                  expanded ? "p-4 leading-relaxed" : "p-2.5",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <FileSearch className="h-3 w-3 shrink-0 text-sky-600" />
                    {link ? (
                      <a
                        href={link}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate font-mono text-xs text-sky-700 hover:underline"
                      >
                        {c.source_ref}
                      </a>
                    ) : (
                      <span className="truncate font-mono text-xs text-foreground/80">{c.source_ref}</span>
                    )}
                    {link && <ExternalLink className="h-2.5 w-2.5 shrink-0 text-muted-foreground" />}
                  </div>
                  <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
                    {confidencePct}%
                  </span>
                </div>
                <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-sky-500"
                    style={{ width: `${confidencePct}%` }}
                  />
                </div>
                <p
                  className={cn(
                    "text-muted-foreground transition-all duration-300 ease-in-out",
                    expanded ? "mt-2.5 text-xs leading-6" : "mt-1.5 text-[11px]",
                  )}
                >
                  {reasonLabel(content.reason)}
                </p>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
