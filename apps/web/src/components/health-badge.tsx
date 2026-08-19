import { cn } from "@/lib/utils";
import { HealthStatus } from "@/lib/types";

const HEALTH_CONFIG: Record<
  HealthStatus,
  { label: string; className: string; pulse?: boolean }
> = {
  healthy: {
    label: "🟢 Healthy",
    className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  },
  p1: {
    label: "🔴 P1 Active",
    className: "bg-red-500/10 text-red-400 border-red-500/30",
    pulse: true,
  },
  p2: {
    label: "🟠 P2 Active",
    className: "bg-orange-500/10 text-orange-400 border-orange-500/30",
    pulse: true,
  },
};

export function HealthBadge({ status }: { status: HealthStatus }) {
  const config = HEALTH_CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium",
        config.className
      )}
    >
      {config.pulse && (
        <span className="relative flex h-1.5 w-1.5">
          <span
            className={cn(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
              status === "p1" ? "bg-red-400" : "bg-orange-400"
            )}
          />
          <span
            className={cn(
              "relative inline-flex h-1.5 w-1.5 rounded-full",
              status === "p1" ? "bg-red-400" : "bg-orange-400"
            )}
          />
        </span>
      )}
      {config.label}
    </span>
  );
}
