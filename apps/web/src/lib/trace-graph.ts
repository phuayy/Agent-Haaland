/**
 * Turns the `trace` evidence row into the ordered steps the trace graph
 * draws: entry point -> every layer the request passed through -> the raise
 * site -> the error it terminated in.
 *
 * Pure and deterministic on purpose. It runs during SSR as well as in the
 * browser, so nothing here may read `Math.random` or the clock — a value
 * that differs between the two renders is a hydration mismatch, and the
 * synthesized fallback below would be exactly that if it were random.
 *
 * The real path comes from apps/api (locate_code writes the row from parsed
 * traceback frames). When the ingested log carried no traceback at all — an
 * alert-shaped incident, the "cold start" case the backend names explicitly
 * — there is no path to draw, and `origin: "inferred"` marks the topology as
 * derived from the service name rather than observed. Callers must surface
 * that distinction: an operator acting on an inferred path believing it was
 * measured is the one failure mode this module can cause.
 */

import type {
  EvidenceItem,
  EvidenceTraceContent,
  IncidentStatus,
  TraceFrame,
} from "@/lib/api/types";

export type TraceLayer =
  | "client"
  | "api"
  | "queue"
  | "worker"
  | "service"
  | "datastore"
  | "external"
  | "function"
  | "error";

export type TraceStepStatus =
  /** The request provably reached here — an earlier frame in the traceback. */
  | "traversed"
  /** The raise site: the deepest frame, where the exception surfaced. */
  | "failed"
  /** The terminal error node carrying the exception class and message. */
  | "error"
  /** Part of a synthesized topology; no evidence the request reached it. */
  | "inferred";

export interface TraceStep {
  id: string;
  label: string;
  layer: TraceLayer;
  status: TraceStepStatus;
  /** "path:line" of the representative frame, for display. */
  location: string | null;
  /** "path:line-line", the shape githubBlobUrl() expects. */
  sourceRef: string | null;
  detail: string | null;
  /** Every frame folded into this step, representative first. */
  frames: TraceFrame[];
}

export interface TraceGraph {
  steps: TraceStep[];
  origin: "traceback" | "inferred";
  exceptionClass: string | null;
  exceptionMessage: string | null;
  /** Frames parsed out of the log, before same-layer runs were collapsed. */
  frameCount: number;
}

/**
 * Statuses at which no diagnosis exists yet. A synthesized path must not
 * accuse a service of being the failure point before the agent has even
 * looked — until then every inferred node is drawn as merely "on the path".
 */
const PRE_DIAGNOSIS_STATUSES: readonly IncidentStatus[] = [
  "detected",
  "enriching",
  "triaging",
];

/**
 * Path/function patterns mapped to the layer they imply, most specific
 * first. Matched against "<path> <function>" lowercased, so both
 * `workers/pricing.py` and `def run_worker` land on `worker`.
 *
 * This is a display heuristic, not a claim about the architecture: a wrong
 * guess mislabels an icon, it never changes the ordering or which node is
 * marked as the failure point.
 */
const LAYER_RULES: readonly { layer: TraceLayer; pattern: RegExp }[] = [
  {
    layer: "queue",
    pattern:
      /(^|[/_.\W])(queues?|celery|arq|kafka|rabbit|amqp|sqs|pubsub|broker|consumers?|producers?|topics?)([/_.\W]|$)/,
  },
  {
    layer: "worker",
    pattern: /(^|[/_.\W])(workers?|tasks?|jobs?|runners?|schedulers?|cron)([/_.\W]|$)/,
  },
  {
    layer: "api",
    pattern:
      /(^|[/_.\W])(routes?|routers?|handlers?|api|endpoints?|controllers?|views?|middlewares?|webhooks?)([/_.\W]|$)/,
  },
  {
    layer: "datastore",
    pattern:
      /(^|[/_.\W])(repositor(y|ies)|daos?|models?|orm|sql|db|database|quer(y|ies)|migrations?|redis|cache|session)([/_.\W]|$)/,
  },
  {
    layer: "external",
    pattern:
      /(^|[/_.\W])(clients?|http|https|requests|httpx|urllib|aiohttp|grpc|soap|integrations?|adapters?|gateways?)([/_.\W]|$)/,
  },
  {
    layer: "service",
    pattern: /(^|[/_.\W])(services?|domain|usecases?|application|agents?|nodes?)([/_.\W]|$)/,
  },
];

/** Keywords in the root cause that point the synthesized failure downstream. */
const DOWNSTREAM_FAILURE_HINT =
  /\b(timeout|timed out|connection|pool|deadlock|redis|query|queries|database|db|latency|slow)\b/i;

const SYNTHETIC_DOWNSTREAMS: readonly { label: string; layer: TraceLayer }[] = [
  { label: "PostgreSQL", layer: "datastore" },
  { label: "Redis", layer: "datastore" },
  { label: "Kafka", layer: "queue" },
  { label: "Upstream API", layer: "external" },
];

function isTraceContent(content: EvidenceItem["content"]): content is EvidenceTraceContent {
  return (
    typeof content === "object" &&
    content !== null &&
    Array.isArray((content as EvidenceTraceContent).frames)
  );
}

/** The `trace` row for an incident, or null if the log yielded no path. */
export function findTraceEvidence(
  evidence: EvidenceItem[] | undefined,
): EvidenceTraceContent | null {
  const row = evidence?.find((e) => e.kind === "trace" && isTraceContent(e.content));
  return row ? (row.content as EvidenceTraceContent) : null;
}

/**
 * The `path:start-end` refs of the located code candidates, which are the
 * only paths known to exist in the repository — see `resolveSourceRef`.
 */
export function findCandidateSourceRefs(evidence: EvidenceItem[] | undefined): string[] {
  return (evidence ?? [])
    .filter((e) => e.kind === "source" && e.source_ref !== null && e.source_ref.includes(":"))
    .map((e) => e.source_ref as string);
}

/**
 * Maps a traceback frame onto a repository-relative ref that can be linked.
 *
 * Frame paths come out of the log as the runtime saw them — container
 * absolutes like `/app/app/pricing.py` — which are not paths in the repo and
 * would produce a confidently broken GitHub link. The located candidates
 * carry the repo-relative form of the same files (the backend resolves them
 * by matching trailing segments), so a frame is linkable exactly when a
 * candidate path is a suffix of it. Anything unmatched stays unlinked rather
 * than guessed: a dead link that looks authoritative is worse than none.
 */
export function resolveSourceRef(frame: TraceFrame, candidateRefs: string[]): string | null {
  const framePath = frame.path.replace(/\\/g, "/");
  for (const ref of candidateRefs) {
    const separator = ref.lastIndexOf(":");
    const candidatePath = ref.slice(0, separator).replace(/\\/g, "/");
    if (framePath === candidatePath || framePath.endsWith(`/${candidatePath}`)) return ref;
  }
  return null;
}

function basename(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  return normalized.slice(normalized.lastIndexOf("/") + 1) || normalized;
}

function frameLabel(frame: TraceFrame): string {
  // `<module>` is a real Python frame but a useless label — it names no
  // function, so fall back to the file that contained it.
  if (!frame.function || frame.function === "<module>") return basename(frame.path);
  return `${frame.function}()`;
}

function layerOf(frame: TraceFrame): TraceLayer {
  const haystack = `${frame.path} ${frame.function ?? ""}`.replace(/\\/g, "/").toLowerCase();
  return LAYER_RULES.find((rule) => rule.pattern.test(haystack))?.layer ?? "function";
}

function stepFromRun(
  frames: TraceFrame[],
  status: TraceStepStatus,
  candidateRefs: string[],
): TraceStep {
  // The run's first frame is the representative one: it is where the request
  // entered this layer, which is what a flow reads as. The rest stay on
  // `frames` so the component can expand them.
  const [head] = frames;
  return {
    id: `frame-${head.depth}`,
    label: frameLabel(head),
    layer: layerOf(head),
    status,
    location: `${head.path}:${head.line}`,
    sourceRef: resolveSourceRef(head, candidateRefs),
    detail: null,
    frames,
  };
}

/**
 * Collapses consecutive frames sharing a layer into one step. A 40-frame
 * Python traceback is mostly framework plumbing repeating the same layer;
 * rendering 40 boxes buries the four that describe the request's actual
 * path. The raise site is never folded — it is the point of the graph.
 */
function collapseByLayer(frames: TraceFrame[], candidateRefs: string[]): TraceStep[] {
  if (frames.length === 0) return [];

  const leading = frames.slice(0, -1);
  const raiseSite = frames[frames.length - 1];

  const steps: TraceStep[] = [];
  let run: TraceFrame[] = [];

  for (const frame of leading) {
    if (run.length > 0 && layerOf(run[0]) !== layerOf(frame)) {
      steps.push(stepFromRun(run, "traversed", candidateRefs));
      run = [];
    }
    run.push(frame);
  }
  if (run.length > 0) steps.push(stepFromRun(run, "traversed", candidateRefs));

  steps.push(stepFromRun([raiseSite], "failed", candidateRefs));
  return steps;
}

/** FNV-1a. Stable across server and client renders, unlike Math.random. */
function hash(value: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/**
 * The path the backend could not observe. Deterministic in `serviceName` so
 * an incident renders the same topology on every poll — a graph that
 * reshuffled every five seconds would read as live data, which is the
 * opposite of the truth.
 */
function inferredGraph(
  serviceName: string,
  status: IncidentStatus,
  rootCauseSummary: string | null,
): TraceGraph {
  const downstream = SYNTHETIC_DOWNSTREAMS[hash(serviceName) % SYNTHETIC_DOWNSTREAMS.length];
  const diagnosed = !PRE_DIAGNOSIS_STATUSES.includes(status);
  const failsDownstream = diagnosed && DOWNSTREAM_FAILURE_HINT.test(rootCauseSummary ?? "");

  const skeleton: { id: string; label: string; layer: TraceLayer }[] = [
    { id: "inferred-client", label: "Client", layer: "client" },
    { id: "inferred-gateway", label: "API Gateway", layer: "api" },
    { id: "inferred-service", label: serviceName, layer: "service" },
    { id: "inferred-downstream", label: downstream.label, layer: downstream.layer },
  ];

  const failingId = failsDownstream ? "inferred-downstream" : "inferred-service";

  return {
    steps: skeleton.map((node) => ({
      ...node,
      status: diagnosed && node.id === failingId ? "failed" : "inferred",
      location: null,
      sourceRef: null,
      detail: null,
      frames: [],
    })),
    origin: "inferred",
    exceptionClass: null,
    exceptionMessage: null,
    frameCount: 0,
  };
}

export interface BuildTraceGraphInput {
  trace: EvidenceTraceContent | null;
  serviceName: string | null;
  status: IncidentStatus;
  rootCauseSummary: string | null;
  /** From `findCandidateSourceRefs` — what makes frames linkable. */
  candidateRefs?: string[];
}

export function buildTraceGraph({
  trace,
  serviceName,
  status,
  rootCauseSummary,
  candidateRefs = [],
}: BuildTraceGraphInput): TraceGraph {
  const frames = trace?.frames ?? [];

  if (frames.length === 0) {
    return inferredGraph(serviceName ?? "this service", status, rootCauseSummary);
  }

  const entry: TraceStep = {
    id: "entry",
    label: serviceName ?? "Request",
    layer: "client",
    status: "traversed",
    location: null,
    sourceRef: null,
    detail: "entry point",
    frames: [],
  };

  const terminal: TraceStep = {
    id: "error",
    label: trace?.exception_class ?? "Unhandled error",
    layer: "error",
    status: "error",
    location: null,
    sourceRef: null,
    detail: trace?.exception_message ?? null,
    frames: [],
  };

  return {
    steps: [entry, ...collapseByLayer(frames, candidateRefs), terminal],
    origin: "traceback",
    exceptionClass: trace?.exception_class ?? null,
    exceptionMessage: trace?.exception_message ?? null,
    frameCount: frames.length,
  };
}
