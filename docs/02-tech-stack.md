# 02 — Technology Stack

Every choice below is stated as: **pick**, the alternatives considered, and why the pick wins *for this project at this stage*. Where a choice is likely to be revisited at scale, that is called out.

---

## 1. Which observability platform to integrate first

This is the highest-leverage decision in the prototype, and the answer is counter-intuitive: **self-host, don't use a SaaS.**

### The bake-off

| Platform | Setup effort | Cost at prototype scale | Push alerting (webhook out) | Log query API | Trace API | Can you break it on cue? |
| --- | --- | --- | --- | --- | --- | --- |
| **Prometheus + Alertmanager + Loki + Tempo** (self-hosted) | ~1 hour, one compose file | Free | ✅ First-class `webhook_config`, no plan gate | ✅ LogQL over HTTP | ✅ TraceQL over HTTP | ✅ Total control |
| **Grafana Cloud** (free tier) | ~30 min | Free to 10k series / 50GB logs | ✅ Contact point → webhook | ✅ Same Loki API | ✅ Same Tempo API | ✅ Good |
| **Sentry** (free tier) | ~20 min, one SDK line | Free to 5k errors/mo | ✅ Alert rule → webhook, plus Internal Integrations | ✅ Issues + events API | ⚠️ Basic performance tracing | ✅ Good |
| **Datadog** | 2–4 hours (agent, tags, monitors) | 14-day trial, then ~$15–31/host/mo | ✅ Webhooks integration | ✅ Logs API (log ingestion is billed) | ✅ APM (billed separately) | ⚠️ Sampling makes demos flaky |
| **Vercel** | 15 min | **Log Drains require Pro (~$20/mo)** | ❌ No alerting webhooks at all | ⚠️ Drains only, push-based | ❌ None | ❌ |
| **Render** | 15 min | Free tier for services | ❌ Only deploy notifications, no metric alerts | ⚠️ Log streams on paid plans | ❌ None | ❌ |

### Verdict

- **Primary: Prometheus + Alertmanager + Loki + Tempo, self-hosted via Docker Compose.**
  Alertmanager's webhook receiver is the single cleanest "push me an incident" contract in the ecosystem — a documented JSON envelope with a stable `fingerprint` field that gives us idempotency for free. Loki and Tempo speak plain HTTP with a query language, no SDK required. Crucially, it is the only option where we can inject a fault and know *exactly* when the alert will fire, which matters enormously for a live demo.

- **Secondary (Phase 2): Sentry.** Highest signal-per-minute-of-setup of any SaaS here. One SDK line per service, and you get exception grouping, release tracking (`sentry-cli releases`), and suspect-commit attribution — which is a second, independent source for "which deploy broke this." Its free tier is genuinely usable.

- **Enterprise adapter (Phase 5): Datadog.** Every target bank already has it. Its API surface is the best of the SaaS options. But it is the wrong thing to build against *first* — the setup cost and the 14-day trial clock will eat prototype time, and sampled APM traces make a demo non-deterministic.

- **Vercel and Render are deployment sources, not observability sources.** Vercel Log Drains are gated behind a paid plan and are push-only with no alerting primitive; Render has no metric alerting webhook. If the frontend is deployed on Vercel, wire its Deploy Hooks in as a *deployment* signal (Section 5), not as detection.

### The consequence: an adapter interface

```python
# apps/api/src/haaland/integrations/base.py
class SignalSource(Protocol):
    """Normalises any monitoring platform's alert into a Signal."""
    def parse(self, raw: dict) -> list[Signal]: ...
    def verify(self, headers: Mapping[str, str], body: bytes) -> bool: ...

class LogSource(Protocol):
    async def query(self, service: str, window: TimeWindow,
                    filters: LogFilters) -> list[LogLine]: ...

class TraceSource(Protocol):
    async def find_exemplar(self, service: str, window: TimeWindow,
                            min_duration_ms: int) -> Trace | None: ...
    async def get_trace(self, trace_id: str) -> Trace: ...
```

`AlertmanagerSource`, `SentrySource`, `DatadogSource` all implement `SignalSource`. The orchestrator never imports a vendor SDK.

---

## 2. Backend language and framework

**Pick: Python 3.12 + FastAPI + uvicorn, managed with `uv`.**

The repo is already Python 3.12 with a `uv`-generated `pyproject.toml`, and the decisive factor is that the entire PII-redaction and LLM-tooling ecosystem (Presidio, LangGraph, the Anthropic SDK's richest surface) is Python-native.

| Alternative | Why not |
| --- | --- |
| **Node/TypeScript (NestJS, Hono)** | One language across the stack is genuinely attractive, and the frontend is TS anyway. But Presidio has no real TS equivalent — you would hand-roll PII detection, which is exactly the part you don't want to hand-roll in a banking product. |
| **Go** | Best raw webhook throughput and single-binary deploys. Wrong ecosystem for the AI layer; you would end up calling out to a Python sidecar for redaction, which is two services instead of one. |
| **Django + DRF** | Admin panel and ORM are nice for a compliance product. Too heavy, and async support is still awkward for the fan-out evidence collection that dominates our latency. |
| **Flask** | Would work, but no native async, no request/response validation, no OpenAPI generation. FastAPI gives all three and generates the TypeScript client for the frontend. |

FastAPI specifically buys: Pydantic v2 validation on every webhook boundary (which is a security control, not a convenience), auto-generated OpenAPI → typed TS client for the frontend, and native `async` so the four parallel evidence queries actually run in parallel.

---

## 3. Agent orchestration

**Pick: LangGraph with a Postgres checkpointer.**

The requirement that decides this: *the workflow must suspend at a human approval gate and survive a process restart.* That is not a prompting problem, it is a durable-execution problem.

LangGraph gives:

- An explicit graph of typed nodes — you can read the incident workflow as code and it matches the diagram in [01-architecture.md](01-architecture.md).
- `interrupt()` / `Command(resume=...)` — a first-class human-in-the-loop primitive. The graph genuinely blocks; it is not a polling loop.
- `PostgresSaver` checkpointing — every state transition is persisted. Restart the worker mid-incident and it resumes at the exact node.
- **The checkpoint history doubles as a debugging trail** for "why did the agent do that."

| Alternative | Why not |
| --- | --- |
| **Raw Anthropic tool-use loop / SDK tool runner** | Genuinely the simplest option and a legitimate fallback. You would then hand-roll suspension: an `incident_state` column, a resume dispatcher, and your own checkpointing. That is reimplementing the 20% of LangGraph we need. Choose this if the team finds LangGraph's abstractions obstructive — the node functions port over almost unchanged. |
| **Temporal** | Strictly the *correct* answer for durable execution at a bank. Deterministic replay, real timers, visibility UI. Rejected for the prototype only because it adds a server, a worker SDK, and a determinism discipline that costs days. **Revisit at Phase 6** — the LangGraph nodes map cleanly onto Temporal activities. |
| **CrewAI / AutoGen** | Multi-agent conversation frameworks. Incident response is a deterministic pipeline with four LLM calls, not a debate between agents. These add non-determinism to the one place we cannot afford it. |
| **Prefect / Airflow** | Batch DAG schedulers. No human-in-the-loop primitive, poor fit for event-triggered sub-minute workflows. |

**Guardrail:** LangGraph nodes must contain no business logic beyond calling a service class. Keep `services/` framework-free so the Temporal migration is a rewrite of the graph file only.

---

## 4. LLM provider and model routing

**Pick: Claude via the official `anthropic` Python SDK. `claude-opus-5` as the default, `claude-haiku-4-5` for the cheap high-frequency path.**

| Task | Model | Reasoning |
| --- | --- | --- |
| Signal noise filter (is this alert even real?) | `claude-haiku-4-5` — $1 / $5 per MTok | Runs on every alert including flapping ones. Must be cheap. |
| Severity classification | `claude-opus-5` — $5 / $25 per MTok | The P1-vs-P3 call is the decision that wakes a human at 3am. Do not economise here. |
| Root cause analysis | `claude-opus-5` | The hardest reasoning task in the product: correlating a metric shape, a log signature, a span waterfall, and a diff. |
| Remediation patch drafting | `claude-opus-5` | Code generation against a real diff. |
| Regression test generation | `claude-opus-5` | Code generation. |
| Post-mortem prose | `claude-sonnet-5` — $3 / $15 per MTok | Summarisation over a structured timeline. Cheaper tier is fine; the facts come from the database, not the model. |

Non-negotiable API usage rules for this codebase:

- **Structured output everywhere.** Every model call uses `client.messages.parse()` with a Pydantic model, or `output_config={"format": {"type": "json_schema", "schema": ...}}`. We never regex a model response. This is a security control (see [09-security-compliance.md](09-security-compliance.md)) as much as a reliability one.
- **Adaptive thinking on the reasoning calls:** `thinking={"type": "adaptive"}` with `output_config={"effort": "high"}` for root cause, `"medium"` for classification. Do **not** pass `budget_tokens` — it is rejected on current models. Do **not** pass `temperature`/`top_p`/`top_k` — also rejected.
- **Prompt caching on the stable prefix.** The system prompt plus the service registry plus runbook excerpts are identical across every incident. Mark the last stable system block with `cache_control={"type": "ephemeral"}`; cache reads cost ~0.1×. Minimum cacheable prefix on `claude-opus-5` is 512 tokens, which our system prompt comfortably exceeds. **Never interpolate a timestamp or incident ID into the system prompt** — it invalidates the whole prefix.
- **Stream anything with `max_tokens` above ~16000** (patch generation, post-mortems) and use `.get_final_message()`.
- Handle `stop_reason == "refusal"` before reading `response.content`.

| Alternative | Why not |
| --- | --- |
| **OpenAI GPT** | Viable. Chosen against because Claude's structured output + prompt caching + adaptive thinking combination fits this workload well, and long-context reasoning over log dumps is a strength. |
| **Self-hosted Llama / Mistral** | The real answer for a bank that refuses egress. Adds GPU infrastructure and a quality regression on the code-generation tasks. Correct Phase 6 option, wrong Phase 1 option. The redaction boundary is designed so this swap is possible. |
| **LiteLLM proxy in front of everything** | Adds a hop and a config surface. Worth it once there are two providers; not yet. |

---

## 5. PII redaction

**Pick: Microsoft Presidio (`presidio-analyzer` + `presidio-anonymizer`) with custom recognisers, plus a reversible token vault in Redis.**

Presidio wins because it is the only mature open-source option that supports **custom pattern recognisers with checksum validation** — which is exactly what banking identifiers need (IBAN mod-97, card PAN Luhn, national ID formats).

The architecture matters more than the library:

```
raw evidence ──▶ Presidio analyze ──▶ replace with stable tokens ──▶ LLM
                        │                     <ACCOUNT_1>
                        ▼
                 token vault (Redis)
                 AES-GCM encrypted
                 24h TTL, keyed by vault_id
                        │
                        ▼
              re-hydrate for HUMAN display only
```

Two rules:

1. The LLM never receives the vault, and never receives a de-tokenised value back.
2. Re-hydration happens in the API response layer, for authenticated humans, and is itself an audited read.

Custom recognisers to write: internal account number format, IBAN, card PAN (Luhn), SWIFT/BIC, national ID (per market), internal customer UUID, session token.

| Alternative | Why not |
| --- | --- |
| **Regex-only** | Fast and dependency-free, and worth having as a *pre*-filter. Fails on names, addresses, and free-text log messages. Insufficient alone for a compliance claim. |
| **spaCy NER directly** | This is what Presidio uses underneath. You would rebuild Presidio's recogniser registry and anonymiser operators yourself. |
| **AWS Comprehend PII / GCP DLP** | Excellent quality, but sends the un-redacted data to a third party to find out what to redact — which defeats the purpose. |
| **Nightfall / Skyflow** | Commercial, correct for production, cost and procurement kill it for a prototype. |

---

## 6. Database

**Pick: Postgres 16 + SQLAlchemy 2.0 (async) + Alembic.**

Postgres because we need: JSONB for heterogeneous evidence payloads, `generated always as identity` monotonic sequences for the hash chain, transactional guarantees around append-only inserts, and full-text search over the timeline. Also `pgvector` is one extension away if runbook RAG lands in Phase 5.

- **SQLAlchemy 2.0 async** with `asyncpg`. Typed `Mapped[]` models, mature migrations.
- **Alembic** for migrations — non-negotiable for a schema that a compliance auditor will read.
- **Append-only enforcement in the database, not the ORM:** a `BEFORE UPDATE OR DELETE` trigger on `incident_events` that raises. Application-level immutability is not a control.

| Alternative | Why not |
| --- | --- |
| **SQLite** | Fine for a single-machine prototype and tempting for zero-ops. No concurrent writers, which breaks the API + worker split. Loses JSONB indexing. |
| **MongoDB** | Schemaless suits the evidence blobs. Loses transactional hash-chain integrity, which is the one thing that must not be eventually consistent. |
| **Supabase / Neon (hosted Postgres)** | Same Postgres, less ops, and Supabase gives Realtime + Storage for free. **A good choice if the team wants managed** — nothing in the schema is self-host-specific. Compose is chosen for offline demo reliability. |
| **TimescaleDB** | Right if we stored metrics ourselves. We don't — Prometheus does. |

---

## 7. Queue and cache

**Pick: Redis 7 + ARQ.**

ARQ is asyncio-native, ~500 lines of concepts, and shares the Redis instance we already need for the PII vault and alert dedupe. Celery is the "grown-up" answer but drags in a synchronous worker model that fights FastAPI's async stack.

Redis carries four distinct jobs here — keep the key namespaces separate:

- `q:*` — ARQ job queue
- `vault:*` — encrypted PII tokens, 24h TTL
- `dedupe:*` — alert fingerprints, 5-minute TTL
- `cache:*` — GitHub API responses, service registry

| Alternative | Why not |
| --- | --- |
| **Celery + RabbitMQ** | Heavier, sync-first, adds a broker. Better at massive scale and complex routing; we need neither. |
| **FastAPI `BackgroundTasks`** | Dies with the process. Unacceptable for a workflow that must survive restarts. |
| **Postgres-backed queue (`pgmq`, SKIP LOCKED)** | One less service, and genuinely fine at our volume. Chosen against only because Redis is already required for the vault. |

---

## 8. Frontend

**Pick: Next.js 15 (App Router) + TypeScript + Tailwind CSS + shadcn/ui.**

- **Next.js** for server components on the incident list (fast first paint on a dashboard someone opens at 3am), route handlers to proxy the backend without CORS, and trivial Vercel deploy.
- **shadcn/ui** because the components are copied into the repo, not installed — a compliance-adjacent product will need to modify them, and you cannot patch a node_modules component.
- **TanStack Query** for server state; **Zustand** only if genuinely needed for cross-component UI state. Do not reach for Redux.
- **`openapi-typescript` + `openapi-fetch`** to generate the client from FastAPI's OpenAPI schema. The backend and frontend types cannot drift.

| Alternative | Why not |
| --- | --- |
| **Vite + React SPA** | Simpler build, no server runtime. Loses SSR and the API proxy; you would hand-roll both. Reasonable if the team dislikes Next. |
| **SvelteKit** | Smaller and faster. Smaller component ecosystem for the specific things we need (graph canvas, code diff viewer). |
| **Streamlit / Gradio** | Would get a demo up in a day. Cannot produce the trace-map and approval UX this product is judged on. |

### Visualisation

| Need | Pick | Alternatives considered |
| --- | --- | --- |
| Service dependency + trace map | **React Flow (`@xyflow/react`)** | Cytoscape.js (better auto-layout, worse React integration), D3 force (full control, weeks of work), vis-network (dated API). React Flow wins because nodes are React components — a service node can render live status, latency, and a deploy badge. |
| Span waterfall | **Custom flex/CSS + `@visx/scale`** | A waterfall is div positioning; a charting library is overkill. |
| Metric sparklines / MTTR charts | **Recharts** | Nivo (prettier defaults, heavier), Chart.js (imperative, awkward in React), visx (more control, more code). |
| Code diff viewer | **`react-diff-viewer-continued`** | Monaco diff editor is far heavier for read-only display. |
| Timeline | Hand-rolled component | No library models an audit chain with actor attribution well. |

---

## 9. Realtime updates

**Pick: Server-Sent Events from FastAPI (`sse-starlette`), backed by Redis pub/sub for multi-worker fan-out.**

Incident updates are strictly server→client. SSE gives auto-reconnect, works through every corporate proxy, and needs no protocol layer.

| Alternative | Why not |
| --- | --- |
| **WebSockets** | Bidirectional capability we don't need, plus connection-state management, plus proxy issues. |
| **Polling** | Simplest, and an acceptable fallback at 5s intervals. Wasteful and makes the dashboard feel dead. |
| **Supabase Realtime / Pusher** | Adds a dependency for something ~40 lines of code does. |

---

## 10. Integration SDKs

| Integration | Pick | Alternatives |
| --- | --- | --- |
| **GitHub** | `githubkit` — async, fully typed from the official OpenAPI spec, native GitHub App auth with installation-token refresh | `PyGithub` (sync, untyped, blocks the event loop); raw `httpx` (you rewrite pagination and JWT rotation) |
| **Slack** | `slack-sdk` (`AsyncWebClient`) + Block Kit, with manual signature verification | `slack-bolt` (a whole framework; we only need two calls and one endpoint); incoming webhooks (no interactivity — fatal, we need buttons) |
| **Jira** | Raw `httpx` against Jira Cloud REST v3 with an API token | `atlassian-python-api` (sync, sprawling), `jira` (sync, dated). Three endpoints do not justify an SDK. |
| **PagerDuty** | Raw `httpx` against Events API v2 | The official SDK wraps a single POST. |
| **Anthropic** | Official `anthropic` SDK | Never raw HTTP in a Python project. |

**Ticketing note:** implement a `TicketProvider` protocol with `JiraProvider` and `LinearProvider`. Linear's GraphQL API is far pleasanter to develop against; Jira is what banks actually run. Support both, demo with whichever is set up.

---

## 11. Testing and quality

| Concern | Pick | Notes |
| --- | --- | --- |
| Test framework | `pytest` + `pytest-asyncio` | |
| HTTP mocking | `respx` | httpx-native, unlike `responses` |
| LLM mocking | Recorded fixtures + a `FakeLLM` implementing the client protocol | Never hit the API in CI. Record real responses once, replay forever. |
| DB tests | `testcontainers-python` | Real Postgres. The hash-chain trigger cannot be tested against SQLite. |
| E2E | Playwright | Drives the dashboard through a full injected incident |
| Lint / format | `ruff` (both) | Replaces black + isort + flake8 |
| Types | `mypy --strict` on `services/`, permissive elsewhere | The business logic is where types pay |
| Frontend | Vitest + React Testing Library | |

**The test that matters most:** a golden-file suite of ~15 recorded incident scenarios (bad deploy, connection-pool exhaustion, downstream timeout, memory leak, cert expiry, …) asserting that classification and root cause are stable. This is the regression net for prompt changes.

---

## 12. Demo microservice estate

**Pick: five FastAPI services, deliberately small, auto-instrumented with `opentelemetry-instrumentation-fastapi`.**

| Service | Role | The failure it can be made to exhibit |
| --- | --- | --- |
| `api-gateway` | Entry point, fans out | Cascading timeout |
| `payments-api` | Calls ledger + auth | Latency injection, 5xx rate |
| `ledger-service` | Owns the DB | Connection-pool exhaustion — the headline demo |
| `auth-service` | Token validation | Cert expiry, slow JWKS fetch |
| `notification-worker` | Async consumer | Queue backlog |

Chaos is injected via a `/chaos` admin endpoint on each service plus a `demo/chaos/` script directory, so a fault is one command and is reproducible on stage.

Instrumentation: `opentelemetry-instrumentation-fastapi` + `-httpx` + `-sqlalchemy` gives distributed traces with zero manual span code. `prometheus-fastapi-instrumentator` exposes RED metrics at `/metrics`.

---

## 13. Summary — the full dependency list

```toml
# apps/api/pyproject.toml — dependencies
fastapi                          # HTTP framework
uvicorn[standard]                # ASGI server
pydantic                         # validation at every boundary
pydantic-settings                # 12-factor config
sqlalchemy[asyncio]              # ORM
asyncpg                          # Postgres driver
alembic                          # migrations
redis                            # queue + vault + cache
arq                              # async task queue
sse-starlette                    # realtime to the dashboard
anthropic                        # Claude
langgraph                        # durable agent state machine
langgraph-checkpoint-postgres    # suspend/resume across restarts
presidio-analyzer                # PII detection
presidio-anonymizer              # PII replacement
githubkit                        # GitHub App, async + typed
slack-sdk                        # Slack Web API + Block Kit
httpx                            # Jira, PagerDuty, Loki, Tempo, Prometheus
cryptography                     # AES-GCM for the token vault
structlog                        # structured JSON logs
opentelemetry-sdk                # self-instrumentation (we dogfood)
jinja2                           # post-mortem templates
weasyprint                       # Markdown/HTML to PDF
python-multipart                 # form-encoded Slack payloads
```

```jsonc
// apps/web/package.json — key dependencies
"next", "react", "react-dom",
"typescript", "tailwindcss",
"@tanstack/react-query",         // server state
"@xyflow/react",                 // trace + dependency map
"recharts",                      // metrics charts
"react-diff-viewer-continued",   // PR diff display
"date-fns",                      // timeline formatting
"zod",                           // runtime validation of API responses
"openapi-fetch",                 // typed client generated from FastAPI
"lucide-react",                  // icons
"sonner"                         // toasts
```
