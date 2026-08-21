"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, LayoutGrid, ListTree } from "lucide-react";
import { useIncidents } from "@/hooks/use-incidents";
import { useServices } from "@/hooks/use-services";
import { READ_ONLY } from "@/lib/api/client";
import { TERMINAL_STATUSES } from "@/lib/api/types";

const NAV = [
  { href: "/incidents", label: "Incidents", icon: ListTree },
  { href: "/", label: "Services", icon: LayoutGrid },
  { href: "/settings/notifications", label: "Notifications", icon: Bell },
];

function NavItem({
  href,
  label,
  icon: Icon,
  count,
  active,
}: {
  href: string;
  label: string;
  icon: typeof ListTree;
  count?: number;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2.5 rounded-lg border-l-2 px-3 py-2 text-[13.5px] font-medium transition-colors ${
        active
          ? "border-blue-500 bg-blue-600/15 text-blue-400"
          : "border-transparent text-sidebar-foreground hover:bg-white/5 hover:text-blue-300"
      }`}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="flex-1">{label}</span>
      {count !== undefined && (
        <span
          className={`rounded-full px-1.5 py-0.5 text-[11px] tabular-nums ${
            active ? "bg-blue-600/25 text-blue-300" : "bg-white/10 text-sidebar-foreground"
          }`}
        >
          {count}
        </span>
      )}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { data: incidents } = useIncidents();
  const { data: services } = useServices();

  const activeCount = incidents?.filter((i) => !(TERMINAL_STATUSES as string[]).includes(i.status)).length ?? 0;
  const degradedCount = services?.filter((s) => s.health !== "healthy").length ?? 0;
  // Proxy-mode builds have no direct origin to name — calls go same-origin
  // through /dash-api (lib/api/client.ts), so the footer says so rather than
  // claiming a localhost backend that this browser never contacts.
  const apiOrigin = READ_ONLY
    ? "same origin · read-only"
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/^https?:\/\//, "");

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col bg-sidebar px-3 py-4 text-sidebar-foreground">
      <div className="flex items-center gap-2.5 px-1 pb-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sidebar-primary text-[13px] font-bold text-sidebar-primary-foreground">
          H
        </div>
        <div className="leading-tight">
          <div className="text-[13.5px] font-semibold text-white">Agent Haaland</div>
          <div className="text-[10px] font-medium tracking-wide text-sidebar-foreground/70 uppercase">
            Incident Operations
          </div>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5">
        {NAV.map((item) => (
          <NavItem
            key={item.href}
            {...item}
            active={item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)}
            count={item.href === "/incidents" ? (incidents?.length ?? 0) : undefined}
          />
        ))}
      </nav>

      <div className="mt-6 border-t border-sidebar-border pt-4">
        <div className="px-1 text-[10px] font-medium tracking-wide text-sidebar-foreground/50 uppercase">
          Incident snapshot
        </div>
        <div className="mt-2 flex flex-col gap-1.5 px-1">
          <div className="flex items-center justify-between text-[13px]">
            <span className="text-sidebar-foreground/80">Active</span>
            <span className="font-semibold tabular-nums text-white">{activeCount}</span>
          </div>
          <div className="flex items-center justify-between text-[13px]">
            <span className="text-sidebar-foreground/80">Services monitored</span>
            <span className="font-semibold tabular-nums text-white">{services?.length ?? 0}</span>
          </div>
          <div className="flex items-center justify-between text-[13px]">
            <span className="text-sidebar-foreground/80">Services degraded</span>
            <span className="font-semibold tabular-nums text-white">{degradedCount}</span>
          </div>
        </div>
      </div>

      <div className="mt-auto flex items-center gap-2 rounded-lg bg-black/15 px-3 py-2.5">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-sidebar-primary" />
        <div className="min-w-0 text-[11.5px] leading-tight">
          <div className="truncate font-medium text-sidebar-foreground/90">{apiOrigin}</div>
          <div className="text-sidebar-foreground/50">Agent Haaland API</div>
        </div>
      </div>
    </aside>
  );
}
