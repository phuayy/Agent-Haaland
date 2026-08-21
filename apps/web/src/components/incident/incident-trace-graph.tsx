"use client";

import { useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Code2,
  Cpu,
  Database,
  ExternalLink,
  Globe,
  Layers,
  Loader2,
  MonitorSmartphone,
  Network,
  Route,
  Waypoints,
} from "lucide-react";
import { useEvidence } from "@/hooks/use-evidence";
import { githubBlobUrl } from "@/lib/api/incidents";
import {
  buildTraceGraph,
  findCandidateSourceRefs,
  findTraceEvidence,
  type TraceLayer,
  type TraceStep,
} from "@/lib/trace-graph";
import type { IncidentStatus } from "@/lib/api/types";

const LAYER_META: Record<TraceLayer, { icon: typeof Network; label: string }> = {
  client: { icon: MonitorSmartphone, label: "Entry" },
  api: { icon: Route, label: "API" },
  queue: { icon: Layers, label: "Queue" },
  worker: { icon: Cpu, label: "Worker" },
  service: { icon: Network, label: "Service" },
  datastore: { icon: Database, label: "Data" },
  external: { icon: Globe, label: "External" },
  function: { icon: Code2, label: "Code" },
  error: { icon: AlertTriangle, label: "Error" },
};

/** Node shell per status. Failure and error nodes share the rose treatment. */
const NODE_STYLE: Record<TraceStep["status"], string> = {
  traversed: "border-emerald-200 bg-white",
  failed: "border-rose-300 bg-rose-50 ring-1 ring-rose-200",
  error: "border-rose-300 bg-rose-50 ring-1 ring-rose-200",
  inferred: "border-slate-200 border-dashed bg-white",
};

const ICON_STYLE: Record<TraceStep["status"], string> = {
  traversed: "bg-emerald-50 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
  error: "bg-rose-100 text-rose-700",
  inferred: "bg-slate-100 text-slate-500",
};

const LABEL_STYLE: Record<TraceStep["status"], string> = {
  traversed: "text-slate-900",
  failed: "text-rose-900",
  error: "text-rose-900",
  inferred: "text-slate-600",
};

function isRose(status: TraceStep["status"]) {
  return status === "failed" || status === "error";
}

function StatusDot({ status }: { status: TraceStep["status"] }) {
  if (status === "inferred") {
    return <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />;
  }
  return (
    <span className={`h-1.5 w-1.5 rounded-full ${isRose(status) ? "bg-rose-500" : "bg-emerald-500"}`} />
  );
}

function FrameLink({
  sourceRef,
  location,
  repoFullName,
  baseRef,
}: {
  sourceRef: string | null;
  location: string;
  repoFullName: string | null;
  baseRef: string | null;
}) {
  const href =
    repoFullName && baseRef && sourceRef ? githubBlobUrl(repoFullName, baseRef, sourceRef) : null;

  if (!href) {
    return <span className="truncate font-mono text-[11px] text-slate-500">{location}</span>;
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex min-w-0 items-center gap-1 font-mono text-[11px] text-sky-700 hover:underline"
    >
      <span className="truncate">{location}</span>
      <ExternalLink className="h-2.5 w-2.5 shrink-0" />
    </a>
  );
}

function TraceNode({
  step,
  isLast,
  repoFullName,
  baseRef,
}: {
  step: TraceStep;
  isLast: boolean;
  repoFullName: string | null;
  baseRef: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta = LAYER_META[step.layer];
  const Icon = meta.icon;
  const foldedFrames = step.frames.slice(1);

  return (
    <li className="relative flex gap-3 pb-3 last:pb-0">
      {/* The rail. It stops at the last node so the flow does not appear to
          continue past the error the request terminated in. */}
      {!isLast && (
        <span
          aria-hidden
          className={`absolute top-8 bottom-0 left-[15px] w-px ${
            isRose(step.status) ? "bg-rose-200" : "bg-slate-200"
          }`}
        />
      )}

      <div
        className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${ICON_STYLE[step.status]}`}
      >
        <Icon className="h-4 w-4" />
      </div>

      <div className={`min-w-0 flex-1 rounded-lg border p-3 shadow-sm ${NODE_STYLE[step.status]}`}>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <StatusDot status={step.status} />
          <span
            className={`truncate font-mono text-[13px] font-semibold ${LABEL_STYLE[step.status]}`}
          >
            {step.label}
          </span>
          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
            {meta.label}
          </span>
          {step.status === "failed" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700">
              <AlertTriangle className="h-2.5 w-2.5" />
              Failure point
            </span>
          )}
        </div>

        {step.location && (
          <div className="mt-1 flex min-w-0">
            <FrameLink
              sourceRef={step.sourceRef}
              location={step.location}
              repoFullName={repoFullName}
              baseRef={baseRef}
            />
          </div>
        )}

        {step.detail && (
          <p
            className={`mt-1 text-[11px] ${
              step.status === "error" ? "font-mono break-words text-rose-800" : "text-slate-500"
            }`}
          >
            {step.detail}
          </p>
        )}

        {foldedFrames.length > 0 && (
          <div className="mt-2">
            <button
              type="button"
              onClick={() => setExpanded((open) => !open)}
              aria-expanded={expanded}
              className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-800"
            >
              {expanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              {foldedFrames.length} more frame{foldedFrames.length === 1 ? "" : "s"} in this layer
            </button>

            {expanded && (
              <ol className="mt-1.5 flex flex-col gap-1 border-l border-slate-200 pl-2.5">
                {foldedFrames.map((frame) => (
                  <li key={frame.depth} className="flex min-w-0 flex-col">
                    <span className="truncate font-mono text-[11px] text-slate-700">
                      {frame.function ?? "—"}
                    </span>
                    <span className="truncate font-mono text-[10px] text-slate-400">
                      {frame.path}:{frame.line}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function Legend({ origin, frameCount }: { origin: "traceback" | "inferred"; frameCount: number }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-200 pt-2.5 text-[11px] text-slate-500">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        Reached
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
        Failure point
      </span>
      <span className="ml-auto inline-flex items-center gap-1.5">
        <Waypoints className="h-3 w-3" />
        {origin === "traceback"
          ? `Derived from ${frameCount} ingested traceback frame${frameCount === 1 ? "" : "s"}`
          : "Inferred topology — no traceback in the ingested logs"}
      </span>
    </div>
  );
}

export function IncidentTraceGraph({
  reference,
  serviceName,
  repoFullName,
  baseRef,
  status,
  rootCauseSummary,
}: {
  reference: string;
  serviceName: string | null;
  repoFullName: string | null;
  baseRef: string | null;
  status: IncidentStatus;
  rootCauseSummary: string | null;
}) {
  const { data, isPending, isError } = useEvidence(reference);

  if (isPending) {
    return (
      <div className="flex h-32 items-center justify-center gap-2 rounded-lg bg-slate-50 text-[13px] text-slate-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Building trace path…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg bg-slate-50 p-4 text-[13px] text-slate-500">
        Could not load the trace path.
      </div>
    );
  }

  const graph = buildTraceGraph({
    trace: findTraceEvidence(data),
    serviceName,
    status,
    rootCauseSummary,
    candidateRefs: findCandidateSourceRefs(data),
  });

  return (
    <div>
      {graph.origin === "inferred" && (
        // Never let a synthesized path pass for a measured one: an operator
        // acting on an inferred topology believing it was observed is the
        // failure mode this component can cause.
        <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] text-amber-800">
          No traceback was found in the ingested logs, so this path is inferred from the service
          registry, not observed. Frames appear here once an incident is ingested with a stack
          trace.
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-4">
        <ol className="flex min-w-[260px] flex-col">
          {graph.steps.map((step, i) => (
            <TraceNode
              key={step.id}
              step={step}
              isLast={i === graph.steps.length - 1}
              repoFullName={repoFullName}
              baseRef={baseRef}
            />
          ))}
        </ol>

        <Legend origin={graph.origin} frameCount={graph.frameCount} />
      </div>
    </div>
  );
}
