import { BrainCircuit, CheckCircle2, ListChecks, Wrench } from "lucide-react";
import { AuditEvent } from "@/lib/types";

export function PostmortemPanel({
  rootCause,
  remediation,
  auditTimeline,
  resolved,
}: {
  rootCause: string;
  remediation: string;
  auditTimeline: AuditEvent[];
  resolved: boolean;
}) {
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto">
      <section className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-violet-300">
          <BrainCircuit className="h-4 w-4" />
          AI Root Cause
        </div>
        <p className="text-sm leading-relaxed text-foreground/90">{rootCause}</p>
      </section>

      <section className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-sky-300">
          <Wrench className="h-4 w-4" />
          Remediation
        </div>
        <p className="text-sm leading-relaxed text-foreground/90">{remediation}</p>
      </section>

      <section className="rounded-lg border border-border p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <ListChecks className="h-4 w-4 text-muted-foreground" />
          Audit Timeline
        </div>
        <ol className="flex flex-col gap-3">
          {auditTimeline.map((event, i) => (
            <li key={i} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={
                    "mt-1 h-2 w-2 shrink-0 rounded-full " +
                    (event.actor === "agent-haaland" ? "bg-violet-400" : "bg-sky-400")
                  }
                />
                {i < auditTimeline.length - 1 && (
                  <span className="w-px flex-1 bg-border" />
                )}
              </div>
              <div className="pb-1">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-mono tabular-nums">{event.time}</span>
                  <span className="font-medium text-foreground/70">{event.actor}</span>
                </div>
                <p className="text-sm leading-snug">{event.action}</p>
              </div>
            </li>
          ))}
          {resolved && (
            <li className="flex gap-3">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              <p className="text-sm font-medium text-emerald-400">
                Incident resolved
              </p>
            </li>
          )}
        </ol>
      </section>
    </div>
  );
}
