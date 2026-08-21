import { cn } from "@/lib/utils";
import { ServiceHealth } from "@/lib/api/types";

const HEALTH_CONFIG: Record<
  ServiceHealth,
  { label: string; className: string; dot: string; pulse?: boolean }
> = {
  healthy: {
    label: "Healthy",
    className: "bg-emerald-50 text-emerald-600 border-emerald-200",
    dot: "bg-emerald-600",
  },
  p1: {
    label: "P1 active",
    className: "bg-rose-50 text-rose-600 border-rose-200",
    dot: "bg-rose-600",
    pulse: true,
  },
  p2: {
    label: "P2 active",
    className: "bg-orange-50 text-orange-700 border-orange-200",
    dot: "bg-orange-500",
    pulse: true,
  },
};

export function HealthBadge({ status }: { status: ServiceHealth }) {
  const config = HEALTH_CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-wide uppercase",
        config.className
      )}
    >
      <span className="relative flex h-1.5 w-1.5">
        {config.pulse && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-75", config.dot)} />
        )}
        <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", config.dot)} />
      </span>
      {config.label}
    </span>
  );
}
