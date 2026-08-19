"use client";

import { BrainCircuit, CircleUser, Clock, Radio } from "lucide-react";
import { useHaalandStore } from "@/lib/store";

function Pill({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-border bg-secondary/50 px-3 py-1.5 text-xs text-secondary-foreground">
      {icon}
      <span className="tabular-nums">{children}</span>
    </div>
  );
}

export function Header() {
  const services = useHaalandStore((s) => s.services);
  const healthyCount = services.filter((s) => s.health === "healthy").length;

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
            <div className="absolute inset-0 rounded-lg bg-primary/40 blur-md" />
            <BrainCircuit className="relative h-5 w-5 text-primary" />
          </div>
          <div className="leading-tight">
            <div className="font-semibold tracking-tight">Agent Haaland</div>
            <div className="text-xs text-muted-foreground">
              Automated Root-Cause Analysis
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Pill icon={<Radio className="h-3.5 w-3.5 text-emerald-400" />}>
            {healthyCount} Services Healthy
          </Pill>
          <Pill icon={<Clock className="h-3.5 w-3.5 text-sky-400" />}>
            30-Day MTTR: 14m
          </Pill>
          <Pill icon={<CircleUser className="h-3.5 w-3.5 text-violet-400" />}>
            on-call: @sre-team
          </Pill>
        </div>
      </div>
    </header>
  );
}
