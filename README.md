# Agent Haaland

**An AI-powered first responder for core banking modernization and incident operations.**

Agent Haaland watches a bank's production estate the way a senior SRE would, except it never sleeps, never loses context switching between dashboards, and never forgets to write the post-mortem.

Designed as an AI-powered first responder for high-stakes environments, it handles the entire triage lifecycle:
- **Instant Triage**: Correlates logs, traces, and deployment history in seconds.
- **Zero-Trust Privacy**: Redacts all customer PII locally before any payload reaches an LLM.
- **Human-in-the-Loop Remediation**: Drafts targeted fixes as Pull Requests, holding execution until an On-Call Lead approves.
- **Automated Compliance**: Assembles an immutable, regulator-ready audit trail in real-time—not after the fact from memory.

---

## Table of Contents

- [Overview](#overview)
- [Key Architectural Notes](#key-architectural-notes)
- [List of Dependencies](#list-of-dependencies)
- [How to Run and Test the Prototype](#how-to-run-and-test-the-prototype)
- [Test the Prototype](#test-the-prototype)

---

## Overview

Modernizing a bank's core systems doesn't just mean rewriting COBOL. It means rethinking how the *humans on call* respond when a modernized, microservice-shaped estate breaks at 3 a.m. Today that response is manual, slow, and undocumented in the moment: an engineer stitches together an APM dashboard, a log viewer, a trace explorer, and the deploy pipeline in their head, fixes the problem, and reconstructs a compliance report days later from Slack scrollback.

**Agent Haaland treats an incident as a durable, auditable workflow instead of a chat transcript.** It is the first responder that arrives before the human does:

1. **Detect & Trace** — correlates the failing service, the blast radius, the exemplar trace, and the deploy that caused it.
2. **Safe AI Triage** — strips PII into reversible tokens *before* anything reaches an LLM, then classifies severity with an auditable rationale.
3. **Human-in-the-Loop Remediation** — an autonomous agent clones the affected repository, locates the faulty code, drafts a patch, runs static checks and generates regression tests, and opens a pull request that **it structurally cannot merge**. A human approves or rejects; the workflow genuinely suspends until they do.
4. **Document & Harden** — the moment an incident closes, the post-mortem is *assembled* from an append-only, hash-chained event log, not written from memory.

The core safety claim of the product: **there is no code path from the agent to production.** Approval is not a policy toggle — the GitHub integration has no `merge()` method at all.

---

## Key Architectural Notes

### Frontend / backend separation

The system is a clean two-tier split:

- **`apps/web`** — a Next.js (App Router) dashboard using a **Master-Detail layout**: the root route (`/`) renders the master view — a searchable grid of registered services with live health state — and drilling into a service's incident opens `/incidents/[id]`, the detail view, which lays out the **Traceback Graph** (a React Flow dependency map with the blast radius highlighted), the **Evidence & Logs** panel (the redacted excerpt the model actually saw), and the **Post-Mortem & AI Analysis** panel side by side.
- **`apps/api`** — a FastAPI service backed by a LangGraph state machine, running as a separate **ARQ worker process** against Postgres and Redis.

### The LLM reasoning loop is isolated from the request/response cycle

This is the single most important backend decision. A full diagnostic run, cloning a repository, running an agentic tool loop over the codebase, drafting a patch, running static analysis, generating and running tests, routinely takes 20–90+ seconds across several LLM calls. An HTTP handler must never block on that.

So the FastAPI layer does exactly three things on `POST /api/debug-sessions` (and every webhook): **verify the request, persist it, enqueue a job on Redis, and return immediately.** The entire LangGraph reasoning loop — `ingest → redact → classify → locate_code → diagnose → evaluate_fixes → apply_patch → static_check → generate_tests → run_tests → push_branch → open_pr → request_approval → generate_report` — executes exclusively inside a dedicated **ARQ worker** (`haaland.worker`), never inside the web server's process.

This buys durability for free: LangGraph's Postgres-backed checkpointer persists the full graph state after every node. If the worker process crashes or is redeployed mid-incident — including while it is suspended waiting on a human's approval — it resumes at the exact node where it left off, with zero lost state.

### HTTP polling for live status updates

The dashboard reflects incident state by **polling the REST API** (`GET /api/incidents`, `GET /api/incidents/{reference}`) on an interval, rather than holding a persistent WebSocket or SSE connection. This is a deliberate trade-off: the incident state machine moves in seconds-to-minutes increments — not a cadence that justifies the connection-management overhead of a socket — so polling keeps the client simple and keeps the number of long-lived connections a security team has to reason about at zero.

### Everything else worth knowing

- **Adapters at the boundary.** GitHub, the LLM provider, and the notification channel are all behind small protocol interfaces, so swapping DeepSeek for Anthropic, or a PAT for a GitHub App installation, is a config change.
- **PII never reaches the model.** A redaction pass replaces account numbers, national IDs, and similar identifiers with stable tokens before the evidence bundle is sent to the LLM; the real values live only in an encrypted, short-TTL vault.
- **Every state transition is an event.** `incident_events` is append-only and hash-chained, so the audit trail can be cryptographically verified, not just trusted.

---

## List of Dependencies

### Languages & runtimes

- **Python 3.12** — backend, managed with **[uv](https://docs.astral.sh/uv/)** as the workspace/package manager
- **Node.js 20+** — frontend

### Backend core

- **FastAPI** + **Uvicorn** — HTTP layer
- **LangGraph** + **langgraph-checkpoint-postgres** — the durable, checkpointed incident state machine
- **SQLAlchemy 2.0 (async)** + **asyncpg** + **Alembic** — ORM and migrations
- **ARQ** — async Redis-backed task queue running the worker
- **Pydantic / pydantic-settings** — request validation and 12-factor configuration
- **cryptography** — encryption for the PII token vault
- **structlog** — structured logging
- **githubkit** — async, typed GitHub App/PAT client for cloning, branching, and opening pull requests
- **GitPython**, **ruff** — workspace cloning and static checks the agent runs against its own patches
- **Presidio** *(optional extra)* — ML-assisted PII detection
- **WeasyPrint** *(optional extra)* — PDF post-mortem export

### AI models / providers

- **DeepSeek** (`deepseek-v4-flash` / `deepseek-v4-pro`) — default real LLM provider, reached via the OpenAI-compatible SDK
- **Anthropic Claude** — supported provider
- **OpenAI GPT** — supported provider
- **Fake provider** — deterministic, zero-network, zero-spend provider used for offline development and CI

### Frontend core

- **Next.js 16** (App Router)
- **React 19** + **TypeScript**
- **Tailwind CSS v4** + **shadcn/ui**
- **Zustand** — client-side state
- **React Flow** (`reactflow`) — the traceback / dependency graph
- **lucide-react** — icons

### Infrastructure

- **PostgreSQL 16** — incidents, the hash-chained audit log, and LangGraph checkpoints
- **Redis 7** — the ARQ job queue and the PII token vault
- **Docker & Docker Compose** — local orchestration of Postgres, Redis, the API, and the worker

### Notifications & integrations

- **Lark / Feishu** (webhook bot or tenant app) — incident and approval cards
- **GitHub** (Personal Access Token or GitHub App) — the only write path out of the agent, scoped to *branch + PR*, never *merge*

---

## How to Run and Test the Prototype

### 1. Clone the repo and install dependencies

```bash
git clone https://github.com/<your-org>/Agent-Haaland.git
cd Agent-Haaland

# Backend — installs one virtual environment for the whole uv workspace
uv sync

# Frontend
cd apps/web
npm install
cd ../..
```

### 2. Set up environment variables

Copy the template below into a `.env` file at the repo root (read by `apps/api/src/haaland/config.py` via `pydantic-settings`, prefix `HAALAND_`):

```bash
# --- Core ---
HAALAND_ENV=dev
HAALAND_DATABASE_URL=postgresql+asyncpg://haaland:haaland@localhost:5432/haaland
HAALAND_REDIS_URL=redis://localhost:6379/0
HAALAND_APP_BASE_URL=http://localhost:8000
HAALAND_SECRET_KEY=change-me
# 32-byte key, base64-encoded — generate with:
#   python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
HAALAND_VAULT_ENCRYPTION_KEY=

# --- LLM provider ---
# `fake` runs the entire pipeline end to end with zero API keys and zero spend —
# recommended for the fastest possible judge setup.
HAALAND_LLM_PROVIDER=fake
HAALAND_DEEPSEEK_API_KEY=
HAALAND_ANTHROPIC_API_KEY=
HAALAND_OPENAI_API_KEY=
HAALAND_MODEL_PRIMARY=deepseek-v4-flash
HAALAND_MODEL_CHEAP=deepseek-v4-flash
HAALAND_MODEL_REPORT=deepseek-v4-pro

# --- GitHub (needed only to see a real PR opened against a real repo) ---
HAALAND_GITHUB_AUTH_MODE=pat
HAALAND_GITHUB_TOKEN=

# --- Notifications (optional) ---
HAALAND_NOTIFY_CHANNELS=

# --- Behaviour ---
HAALAND_CORS_ORIGINS=*
```

Generate the two required secrets with:

```bash
python -c "import secrets;print(secrets.token_urlsafe(32))"                                  # HAALAND_SECRET_KEY
python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"   # HAALAND_VAULT_ENCRYPTION_KEY
```

### 3. Boot up the backend and frontend simultaneously

**Terminal 1 — infrastructure (Postgres + Redis):**

```bash
docker compose up -d postgres redis
```

**Terminal 2 — database migrations, then the API:**

```bash
cd apps/api
uv run alembic upgrade head
uv run uvicorn haaland.main:app --reload
```

**Terminal 3 — the worker (not optional — this is where the LangGraph reasoning loop actually runs):**

```bash
cd apps/api
uv run arq haaland.worker.WorkerSettings
```

**Terminal 4 — the frontend:**

```bash
cd apps/web
npm run dev
```

The dashboard is now live at **http://localhost:3000**, and the API at **http://localhost:8000** (interactive docs at `/docs`).

---

## Test the Prototype

There are two ways to see Agent Haaland work, depending on how much time you have:

### Fast path — see the UI in 30 seconds (no credentials required)

1. Open **http://localhost:3000**.
2. Find any service card on the dashboard (the master view).
3. Click **"Simulate Incident."**
4. Click into the incident that appears. You'll land on the detail view showing:
   - The **Traceback Graph** — the dependency map with the failing service highlighted and the blast-radius edges animated.
   - **Evidence & Logs** — the captured stack trace for the injected fault.
   - **Post-Mortem & AI Analysis** — the AI-generated root cause and remediation summary, with the audit timeline of every step the agent took.

This path requires zero configuration — no LLM key, no GitHub token — and is the quickest way to see the trace map and triage UI in action.

### Full path — trigger the real agent against a real repository

To watch the actual backend pipeline run — cloning a repository, diagnosing a genuine bug with an LLM, drafting a patch, and opening a real pull request — use the bundled broken demo service:

```bash
# One-time: push demo/seed_repo to a GitHub repo you control, then point
# demo/seed_repo/sample_request.json's repo_url at it. With
# HAALAND_LLM_PROVIDER=fake, this runs end to end with zero API spend.

curl -sS -X POST localhost:8000/api/debug-sessions \
  -H 'content-type: application/json' \
  -d @demo/seed_repo/sample_request.json
```

This returns `202 Accepted` with an incident `reference` immediately — the worker takes it from there. Poll its progress with:

```bash
curl -sS localhost:8000/api/incidents/<reference>
```

Watch the `status` field move through the pipeline (`detected` → `triaging` → `diagnosing` → `awaiting_approval`), then approve the drafted fix so the workflow completes:

```bash
curl -sS -X POST localhost:8000/api/incidents/<reference>/approve \
  -H 'content-type: application/json' \
  -d '{"actor": "judge@hackathon", "reason": "looks correct"}'
```

Finally, verify the tamper-evident audit trail and the generated post-mortem:

```bash
curl -sS localhost:8000/api/incidents/<reference>/audit/verify
curl -sS localhost:8000/api/incidents/<reference>/postmortem
```
