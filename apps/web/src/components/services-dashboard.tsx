"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, LayoutGrid, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ServiceCard } from "@/components/service-card";
import { AddServiceDialog } from "@/components/add-service-dialog";
import { useServices } from "@/hooks/use-services";
import { READ_ONLY } from "@/lib/api/client";

function CardSkeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-4 rounded-xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-2">
          <div className="h-3.5 w-32 rounded bg-muted" />
          <div className="h-2.5 w-20 rounded bg-muted" />
        </div>
        <div className="h-5 w-14 rounded-full bg-muted" />
      </div>
      <div className="h-3 w-44 rounded bg-muted" />
      <div className="h-6 w-24 rounded-full bg-muted" />
      <div className="h-8 w-full rounded bg-muted" />
    </div>
  );
}

export function ServicesDashboard() {
  const [query, setQuery] = useState("");
  const { data: services, isPending, isError, error, isFetching, refetch } = useServices();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!services) return [];
    if (!q) return services;
    return services.filter((s) =>
      [s.name, s.owner_team ?? "", s.repo_full_name ?? ""].some((field) =>
        field.toLowerCase().includes(q)
      )
    );
  }, [services, query]);

  const total = services?.length ?? 0;
  const unhealthy = services?.filter((s) => s.health !== "healthy").length ?? 0;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-7 px-8 py-9">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Service Registry
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Services</h1>
          <p className="text-sm text-muted-foreground">
            {isPending ? (
              "Loading the registry…"
            ) : (
              <>
                <span className="tabular-nums text-foreground/70">{total}</span> registered
                microservice{total === 1 ? "" : "s"} under monitoring
                {unhealthy > 0 && (
                  <>
                    {" · "}
                    <span className="font-medium text-rose-600 tabular-nums">{unhealthy}</span>{" "}
                    with an open incident
                  </>
                )}
              </>
            )}
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
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh now (the registry also polls every 10s)"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          </Button>
          <AddServiceDialog />
        </div>
      </div>

      {isPending && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}

      {isError && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-rose-200 bg-rose-50/60 py-16 text-center">
          <AlertTriangle className="h-5 w-5 text-rose-500" />
          <div className="flex flex-col gap-1">
            <p className="text-sm font-medium text-foreground">Couldn&apos;t load the registry</p>
            <p className="text-sm text-muted-foreground">{error.message}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      )}

      {!isPending && !isError && total === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-20 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <LayoutGrid className="h-4.5 w-4.5" />
          </div>
          <div className="flex flex-col gap-1">
            <p className="text-sm font-medium text-foreground">No services registered yet</p>
            <p className="text-sm text-muted-foreground">
              {READ_ONLY
                ? "This dashboard is read-only. Seed the registry with `make seed`, or POST /api/services with your bearer token."
                : "Add one to start triggering debug sessions."}
            </p>
          </div>
          <div className="mt-1">
            <AddServiceDialog />
          </div>
        </div>
      )}

      {!isPending && !isError && total > 0 && (
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
