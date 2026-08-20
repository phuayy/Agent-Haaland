"use client";

import { useMemo, useState } from "react";
import { LayoutGrid, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { ServiceCard } from "@/components/service-card";
import { AddServiceDialog } from "@/components/add-service-dialog";
import { useHaalandStore } from "@/lib/store";

export function ServicesDashboard() {
  const [query, setQuery] = useState("");
  const services = useHaalandStore((s) => s.services);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return services;
    return services.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.ownerTeam.toLowerCase().includes(q) ||
        s.repoUrl.toLowerCase().includes(q)
    );
  }, [services, query]);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-7 px-8 py-9">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Service Registry
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Services</h1>
          <p className="text-sm text-muted-foreground">
            <span className="tabular-nums text-foreground/70">{services.length}</span> registered
            microservice{services.length === 1 ? "" : "s"} under monitoring
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search services…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-56 pl-8"
            />
          </div>
          <AddServiceDialog />
        </div>
      </div>

      {services.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-20 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <LayoutGrid className="h-4.5 w-4.5" />
          </div>
          <div className="flex flex-col gap-1">
            <p className="text-sm font-medium text-foreground">No services registered yet</p>
            <p className="text-sm text-muted-foreground">Add one to start triggering debug sessions.</p>
          </div>
          <div className="mt-1">
            <AddServiceDialog />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((service) => (
            <ServiceCard key={service.id} service={service} />
          ))}
          {filtered.length === 0 && (
            <p className="col-span-full py-16 text-center text-sm text-muted-foreground">
              No services match &ldquo;{query}&rdquo;.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
