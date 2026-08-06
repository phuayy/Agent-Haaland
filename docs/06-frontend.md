# 06 — Frontend

## What the UI is for

Three audiences, three jobs:

| Audience | Job | Must be achievable in |
|---|---|---|
| On-call engineer, woken at 03:00 | Understand and decide | **60 seconds** |
| Service owner, next morning | Understand what their deploy did | 5 minutes |
| Compliance officer, next quarter | Prove the controls operated | 2 minutes, exportable |

The dominant constraint is the first one. Everything on the incident detail page is ordered by "what does a tired person need first."

---

## Information architecture

```
/                          → redirect to /incidents
/incidents                 → live incident feed (the default screen)
/incidents/[reference]     → incident detail
   ├── (default tab)       → Overview: root cause, evidence, actions
   ├── /trace              → Trace map + span waterfall
   ├── /timeline           → Full audit chain, verifiable
   ├── /remediation        → PR diff + approval controls
   └── /postmortem         → Generated report, export
/services                  → Service registry + dependency graph + health
/services/[name]           → Service detail, deploy history, incident history
/analytics                 → MTTD/MTTA/MTTR trends, noisiest services, AI accuracy
/settings
   ├── /integrations       → connection status for each integration
   ├── /prompts            → prompt versions currently live (read-only)
   └── /users              → approvers and roles
```

Deliberately absent: a chat interface. Nothing about this workflow is improved by making an engineer type at 3am.

---

## Page specs

### `/incidents` — the feed

Layout: a filter bar, then a virtualised list. Live-updated over SSE.

Each row, left to right:
- Severity pill, colour-coded, with a pulsing dot if the incident is active
- Reference (`INC-2026-0042`) and title
- Affected services as chips
- Status badge (see state machine in [01-architecture.md](01-architecture.md))
- Relative time since detection, live-ticking
- **An action affordance if the incident needs the viewer**: `Awaiting your approval` as a primary button

Filters: status, severity, service, date range, and `needs my attention` (default on for users with the `approver` role).

The empty state matters more than usual — most of the time there are no active incidents. It should show a green all-clear with the count of services monitored and time since the last incident, not a shrug.

### `/incidents/[reference]` — Overview tab

Vertical order is fixed and is the product's opinion about what matters:

1. **Severity + status header.** One line: what is broken, how bad, what phase we are in.
2. **Root cause card.** The model's `root_cause` prose, the confidence as a bar, the category, and the culprit deploy as a clickable commit link. If confidence is below 0.5, this card renders in a warning style with "low confidence — verify before acting."
3. **The decision, if one is pending.** Approve / Reject buttons and a link to the PR diff. This is the only interactive element above the fold.
4. **Evidence accordion.** Collapsed by default, four sections: Logs, Trace, Deployments, Metrics. Each shows what the model actually saw — the redacted excerpt from `evidence.content` — with a link to the source system.
5. **Impact strip.** Affected services, estimated blast radius, customer-impact classification.
6. **Reasoning disclosure.** A `Show AI reasoning` toggle rendering the summarised thinking, the model used, prompt version, tokens, and cost. Collapsed by default; present because trust requires it to be inspectable.

**PII rehydration:** tokens like `<ACCOUNT_1>` render as a masked chip `ACC •••301` with a click-to-reveal that requires the viewer's role and writes an audit event. Reveal fails after the 24h vault TTL, with an explanatory message rather than an error.

### `/incidents/[reference]/trace`

Two panels, split vertically.

**Top — service map (React Flow).** Nodes are services; edges are calls. Node rendering encodes state:

- Border colour: health (green / amber / red)
- Badge: p99 latency in the incident window
- Deploy marker: a small icon if the service was deployed within the correlation window, red if it is the suspected culprit
- Node size: request volume

Edges are weighted by call volume and coloured by error rate. The culprit path — from entry point to the failing span — is highlighted and animated. Layout is computed with `dagre` (left-to-right), then frozen; auto-layout that reshuffles on every render is disorienting.

Custom node component sketch:

```tsx
function ServiceNode({ data }: NodeProps<ServiceNodeData>) {
  return (
    <div className={cn(
      "rounded-lg border-2 bg-card px-3 py-2 shadow-sm min-w-[160px]",
      data.health === "critical" && "border-destructive animate-pulse",
      data.health === "degraded" && "border-warning",
      data.health === "healthy"  && "border-border",
      data.isCulprit && "ring-2 ring-destructive ring-offset-2",
    )}>
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center gap-2">
        <span className="font-medium text-sm">{data.name}</span>
        {data.deployedInWindow && <GitCommitIcon className="h-3 w-3 text-destructive" />}
      </div>
      <div className="text-xs text-muted-foreground tabular-nums">
        p99 {data.p99Ms}ms · {data.errorRatePct}% err
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
```

**Bottom — span waterfall.** Standard flame layout: one row per span, indented by depth, bar width proportional to duration, positioned by start offset. Self-time is shown in a darker shade within each bar — this is the number that identifies the culprit and it should be visually obvious, not derived by the reader. Clicking a span opens attributes and the related log lines.

No charting library. This is absolute positioning with computed percentages, ~150 lines, and full control.

### `/incidents/[reference]/timeline`

The compliance view, and the one to show a regulator.

A vertical timeline, one entry per `incident_events` row, showing: timestamp (absolute UTC + relative), actor with a type icon (⚙️ system / 🤖 AI / 👤 human / 🔗 integration), the summary line, and an expandable payload viewer.

At the top: an **integrity banner**. It calls `GET /api/incidents/{id}/audit/verify` and renders either a green "Audit chain verified — 34 events, unbroken" or a red divergence report naming the first bad sequence number. This banner is the single most persuasive element in the entire product for a compliance audience.

Filter by actor type. Export as CSV or JSON.

### `/incidents/[reference]/remediation`

Left: the diff, rendered with `react-diff-viewer-continued`, split view on desktop and unified on mobile, with the PR title and body above it.

Right: a decision panel showing risk assessment, verification steps, rollback instructions, and the approval controls. Rejecting requires a reason — the textarea is mandatory, because "why was this rejected" is a question the post-mortem must answer.

If the viewer lacks the `approver` role, the buttons are replaced with "Awaiting approval from @on-call" and a nudge action.

For tier-1 services with two-approver policy, the panel shows `1 of 2 approvals` and the identity of the first approver, and disables the button for that same user.

### `/analytics`

Four cards and three charts, using Recharts:

- MTTD, MTTA, MTTR — current 30-day median with sparkline and delta versus previous period
- Incidents by severity over time (stacked area)
- Noisiest services (horizontal bar) — drives the "which service needs investment" conversation
- **AI accuracy panel**: severity agreement rate (did a human change the severity?), culprit-deploy precision, approval rate of drafted remediations. This is the honesty panel, and it should be prominent. A product that makes AI claims must show its own hit rate.

---

## Realtime

SSE, one connection per browser tab, subscribing to a filtered stream.

```ts
// apps/web/src/hooks/use-incident-stream.ts
export function useIncidentStream(incidentId?: string) {
  const qc = useQueryClient();
  useEffect(() => {
    const url = incidentId ? `/api/stream/incidents/${incidentId}` : `/api/stream/incidents`;
    const es = new EventSource(url);

    es.addEventListener("incident.updated", (e) => {
      const patch = JSON.parse(e.data);
      qc.setQueryData(["incident", patch.reference], (old) => ({ ...old, ...patch }));
    });
    es.addEventListener("event.appended", (e) => {
      const ev = JSON.parse(e.data);
      qc.setQueryData(["timeline", ev.incident_id], (old = []) => [...old, ev]);
    });
    es.addEventListener("incident.created", () => {
      qc.invalidateQueries({ queryKey: ["incidents"] });
      toast.error("New incident detected");
    });

    return () => es.close();
  }, [incidentId, qc]);
}
```

Server side, `sse-starlette` reading from a Redis pub/sub channel so any worker can publish and every API replica fans out:

```python
@router.get("/stream/incidents/{incident_id}")
async def stream(incident_id: UUID, user: User = Depends(current_user)):
    async def gen():
        async with redis.pubsub() as ps:
            await ps.subscribe(f"incident:{incident_id}")
            yield {"event": "snapshot", "data": (await get_incident(incident_id)).json()}
            async for msg in ps.listen():
                if msg["type"] == "message":
                    yield {"event": json.loads(msg["data"])["type"], "data": msg["data"]}
    return EventSourceResponse(gen(), ping=15)
```

Heartbeat every 15s to survive proxy idle timeouts. `EventSource` reconnects automatically; on reconnect the client refetches to close the gap, because SSE has no replay.

---

## Type safety across the boundary

FastAPI emits OpenAPI; we generate the client. The frontend never hand-writes an API type.

```jsonc
// apps/web/package.json
"scripts": {
  "gen:api": "openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts"
}
```

```ts
import createClient from "openapi-fetch";
import type { paths } from "@/lib/api/schema";

export const api = createClient<paths>({ baseUrl: "/api" });

// Fully typed, including the response shape
const { data, error } = await api.GET("/incidents/{reference}", {
  params: { path: { reference: "INC-2026-0042" } },
});
```

`gen:api` runs in CI against a booted backend; a drift between backend and frontend types fails the build rather than surfacing at runtime.

---

## Visual design notes

- **Dark mode is the default.** Incident tooling is used at night, in dark rooms, next to a terminal.
- **Severity colour is the only saturated colour on the page.** P1 red, P2 orange, P3 amber, P4 slate. Everything else is neutral. If the whole interface is colourful, severity stops communicating.
- **Never rely on colour alone** — every severity pill carries its text label, for accessibility and for printed compliance exports.
- **Tabular numbers everywhere** (`font-variant-numeric: tabular-nums`) for latencies, counts, and timestamps, so scanning a column of numbers works.
- **Timestamps: absolute UTC plus relative.** `09:12:03 UTC (4m ago)`. Relative alone is useless in a post-mortem; absolute alone is useless during an incident.
- **No skeleton-loader theatre on the incident feed.** Server-render the first page. A tired engineer opening the dashboard should see incidents, not grey rectangles.

## Component inventory

| Component | Notes |
|---|---|
| `SeverityBadge` | Pill, colour + label |
| `IncidentStatusBadge` | Maps the 14 statuses to 5 visual groups |
| `IncidentRow` / `IncidentList` | Virtualised over `@tanstack/react-virtual` |
| `RootCauseCard` | Includes the confidence bar and low-confidence warning state |
| `EvidenceAccordion` | Four typed sections with source links |
| `ServiceMap` | React Flow wrapper, dagre layout, frozen positions |
| `ServiceNode` | Custom React Flow node |
| `SpanWaterfall` | Hand-rolled, self-time shading |
| `AuditTimeline` | Event list with actor icons |
| `ChainIntegrityBanner` | Calls the verify endpoint |
| `ApprovalPanel` | Buttons, mandatory reject reason, two-approver state |
| `DiffViewer` | Wraps `react-diff-viewer-continued` |
| `RedactedValue` | Masked chip with audited click-to-reveal |
| `AiReasoningDisclosure` | Collapsible, shows model/version/cost |
| `CostBadge` | Per-incident LLM spend |
| `MetricSparkline` | Recharts, for the analytics cards |

## Accessibility and export

- Every interactive element keyboard-reachable; approval buttons carry `aria-describedby` pointing at the risk assessment.
- The timeline and post-mortem pages have a print stylesheet — compliance officers print things.
- Post-mortem export produces both Markdown (for the wiki) and PDF (for the filing).
