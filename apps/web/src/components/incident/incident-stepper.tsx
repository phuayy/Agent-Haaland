import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { IncidentStatus } from "@/lib/api/types";

const STAGES = ["Detected", "Diagnosing", "Awaiting approval", "Closed"] as const;

const STAGE_INDEX: Record<IncidentStatus, number> = {
  detected: 0,
  enriching: 0,
  triaging: 1,
  diagnosing: 1,
  awaiting_approval: 2,
  approved: 2,
  remediating: 2,
  verifying: 2,
  documenting: 2,
  closed: 3,
  triaged_low: 3,
  rejected: 3,
  failed: 3,
  escalated: 3,
};

const STOPPED = new Set<IncidentStatus>(["rejected", "failed", "escalated"]);

export function IncidentStepper({ status }: { status: IncidentStatus }) {
  const currentIndex = STAGE_INDEX[status];
  const stopped = STOPPED.has(status);

  return (
    <div className="flex items-center">
      {STAGES.map((stage, i) => {
        const isComplete = i < currentIndex || (i === currentIndex && !stopped && status !== "awaiting_approval" && currentIndex === 3);
        const isCurrent = i === currentIndex;
        const isStoppedHere = isCurrent && stopped;
        const isLast = i === STAGES.length - 1;

        return (
          <div key={stage} className={cn("flex items-center", !isLast && "flex-1")}>
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold",
                  isStoppedHere && "border-rose-400 bg-rose-50 text-rose-600",
                  !isStoppedHere && isComplete && "border-primary bg-primary text-primary-foreground",
                  !isStoppedHere && isCurrent && !isComplete && "border-primary bg-primary/10 text-primary",
                  !isStoppedHere && !isComplete && !isCurrent && "border-border bg-muted text-muted-foreground"
                )}
              >
                {isStoppedHere ? (
                  <X className="h-3 w-3" />
                ) : isComplete ? (
                  <Check className="h-3 w-3" />
                ) : (
                  i + 1
                )}
              </div>
              <span
                className={cn(
                  "text-center text-[11px] font-medium whitespace-nowrap",
                  isCurrent ? "text-foreground" : "text-muted-foreground"
                )}
              >
                {isStoppedHere ? status[0].toUpperCase() + status.slice(1) : stage}
              </span>
            </div>
            {!isLast && (
              <div
                className={cn("mx-2 h-0.5 flex-1 rounded-full", i < currentIndex ? "bg-primary" : "bg-border")}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
