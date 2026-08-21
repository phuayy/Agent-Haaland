"use client";

import { Download, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { usePostmortem } from "@/hooks/use-postmortem";
import { postmortemMarkdownUrl } from "@/lib/api/incidents";

export function PostmortemPanel({ reference }: { reference: string }) {
  const { data, isPending, isError } = usePostmortem(reference);

  if (isPending) {
    return (
      <div className="flex items-center gap-2 p-4 text-[13px] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Checking for a post-mortem…
      </div>
    );
  }

  if (isError) {
    return <p className="p-4 text-[13px] text-muted-foreground">Could not load the post-mortem.</p>;
  }

  if (!data) {
    return (
      <p className="p-4 text-[13px] text-muted-foreground">
        Not generated yet — the post-mortem is assembled once the incident is documented.
      </p>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="tabular-nums">
          v{data.version} · generated {new Date(data.generated_at).toLocaleString()}
        </span>
        <a
          href={postmortemMarkdownUrl(reference)}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-sky-700 hover:underline"
        >
          <Download className="h-3.5 w-3.5" />
          Export Markdown
        </a>
      </div>
      <div
        className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-border bg-muted/60 p-4 text-[13.5px] leading-relaxed
          [&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-base [&_h1]:font-semibold [&_h1]:first:mt-0
          [&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:first:mt-0
          [&_h3]:mt-3 [&_h3]:mb-1.5 [&_h3]:text-sm [&_h3]:font-medium
          [&_p]:mb-3 [&_p]:text-foreground/90
          [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:mb-1
          [&_a]:text-sky-700 [&_a]:hover:underline
          [&_code]:rounded [&_code]:bg-secondary [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs
          [&_strong]:font-semibold"
      >
        <ReactMarkdown>{data.markdown}</ReactMarkdown>
      </div>
    </div>
  );
}
