"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
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
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Services</h1>
          <p className="text-sm text-muted-foreground">
            {services.length} registered microservices under monitoring
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search services..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-56 pl-8"
            />
          </div>
          <AddServiceDialog />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map((service) => (
          <ServiceCard key={service.id} service={service} />
        ))}
        {filtered.length === 0 && (
          <p className="col-span-full py-12 text-center text-sm text-muted-foreground">
            No services match &ldquo;{query}&rdquo;.
          </p>
        )}
      </div>
    </div>
  );
}
