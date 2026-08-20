"use client";

import { Bot, Link2, Loader2, Settings2, User } from "lucide-react";
import { useAuditTimeline } from "@/hooks/use-audit-timeline";
import type { ActorType } from "@/lib/api/types";

const ACTOR_ICON: Record<ActorType, React.ReactNode> = {
  system: <Settings2 className="h-3 w-3" />,
  ai: <Bot className="h-3 w-3" />,
  human: <User className="h-3 w-3" />,
  integration: <Link2 className="h-3 w-3" />,
};

const ACTOR_DOT: Record<ActorType, string> = {
  system: "bg-slate-400",
  ai: "bg-violet-400",
  human: "bg-sky-400",
  integration: "bg-amber-400",
};

function formatOccurredAt(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function AuditTimeline({ reference }: { reference: string }) {
  const { data, isPending, isError } = useAuditTimeline(reference);

  if (isPending) {
    return (
      <div className="flex items-center gap-2 p-4 text-[13px] text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Loading timeline…
      </div>
    );
  }

  if (isError) {
    return <p className="p-4 text-[13px] text-muted-foreground">Could not load the audit timeline.</p>;
  }

  if (!data || data.length === 0) {
    return <p className="p-4 text-[13px] text-muted-foreground">No events recorded yet.</p>;
  }

  return (
    <ol className="flex flex-col gap-3">
      {data.map((event, i) => (
        <li key={event.seq} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span
              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-black/70 ${ACTOR_DOT[event.actor_type]}`}
              title={event.actor_type}
            >
              {ACTOR_ICON[event.actor_type]}
            </span>
            {i < data.length - 1 && <span className="w-px flex-1 bg-border" />}
          </div>
          <div className="pb-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-mono tabular-nums">{formatOccurredAt(event.occurred_at)}</span>
              <span className="font-medium text-foreground/70">{event.actor_label}</span>
            </div>
            <p className="text-[13.5px] leading-snug text-foreground/90">{event.summary}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
