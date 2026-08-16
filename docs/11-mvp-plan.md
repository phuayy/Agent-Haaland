# 11 — MVP Starter Plan

Documents 00–10 describe the finished product. This one describes the **smallest thing that is recognisably that product**, and the order to build it in.

It is a companion to [08-roadmap.md](08-roadmap.md), not a replacement. The roadmap's Phases 0–4 are ~18 focused days. This plan cuts that to **~15 days by deleting scope the demo never touches**, and front-loads the external dependencies that will otherwise stall you on day 9.

---

## The MVP, stated as a single sentence

> One chaos command produces one incident that a human approves in Slack and that closes with an assembled, hash-verified post-mortem — where the model never saw an account number and never had the ability to merge.

If a build can do that on a cold start, it is the product. Everything else in docs 00–10 is breadth.

### The irreducible core

Doc 08 names three things that must never be cut. They are the MVP:

1. **The redaction boundary** — the compliance claim.
2. **The append-only hash chain** — the audit claim.
3. **The human approval gate** — the safety claim.

Plus the spine that connects them: alert webhook → evidence fan-out → one diagnosis → one PR → one dashboard.

---

## Scope cuts

Everything below is in docs 00–10 and **out of the MVP**. Each cut is justified against the demo in [10-demo-script.md](10-demo-script.md).

| Full spec | MVP | Why it's safe to cut |
|---|---|---|
| 5 demo microservices | **2**: `payments-api` → `ledger-service` | The headline fault needs exactly one pair where *the alert fires on A and the fault is in B*. `api-gateway`, `auth-service`, `notification-worker` add compose surface and zero demo value. Add them back in a day when you want the blast-radius story. |
| Grafana in the obs stack | **drop** | It exists "for our own debugging" (doc 07). You have `psql` and the Loki/Tempo HTTP APIs. |
| Haiku noise-filter stage (doc 05, stage 1a) | **drop** | Redis fingerprint dedupe plus `for: 1m` on the alert rules already suppress flapping. A second model path with its own prompt file, cost row, and failure mode buys nothing until you have real alert volume. |
| Jira / `TicketProvider` / P3–P4 path | **drop** | The P3/P4 branch can `status = triaged_low` and stop. Doc 08's own cut list ranks Jira 4th. |
| PagerDuty | **drop** | Slack carries notification. One integration to wire, not two. |
| Per-incident Slack channel (`conversations.create`) | **drop** | The approval card alone carries Beat 4. Needs `channels:manage`, which is the scope most likely to be refused by a corporate workspace admin. |
| Regression test generation + sandbox validation | **drop** | Doc 08 ranks it 2nd on the cut list. The pre-fix-fails/post-fix-passes harness is a day of work for a 20-second demo beat. |
| `/analytics` page | **drop** | Needs closed incidents to be interesting. You will have three. |
| Sentry / Datadog / Linear / GitLab adapters | **drop** | Write the `Protocol`s (they cost ~40 lines and shape everything downstream). Implement exactly one concrete class each. |
| Runbook RAG + `pgvector` | **drop** | Phase 5 in the roadmap, and correctly so. |
| Four-eyes approval, multi-signal correlation, flapping suppression | **drop** | All are refinements of a gate that must first exist. |
| 15-scenario eval suite | **3 scenarios** | `bad_deploy_pool_size`, `flapping_alert_no_impact`, `prompt_injection_in_logs`. The third is a release gate and is non-negotiable; the other two prove the harness works. |
| Full frontend IA (7 route groups) | **4 views**: feed, overview, trace, timeline, remediation | Collapse `/postmortem` into a tab on the overview. Drop `/services`, `/analytics`, `/settings` entirely. |
| React Flow service map | **stretch within the trace view** | The **span waterfall** is the moment the audience understands the product (Beat 2), and it is ~150 lines of absolutely-positioned divs with no library. Build the waterfall first; the dependency map is polish. |

### What is *not* cut, despite being tempting

- **Tempo.** The trace waterfall is the single most persuasive screen. Keep it, and keep the Jaeger fallback in your back pocket (doc 08 flags Tempo search as the flakiest dependency; it is one line in `TraceSource`).
- **LangGraph + Postgres checkpointer.** The kill-the-worker-and-resume demo is the hardest engineering claim in the product. It does not survive being deferred.
- **`ai_analyses` with prompt version + hash.** One extra table write per model call, and it is the entire model-risk-management story.
- **The full `incident_status` enum.** Statuses are cheap; *transitions* are code. Put all 14 values into migration `0001` (Postgres enums are painful to alter later) and wire only the happy path plus reject.

---

## Day 0 — unblock the external dependencies before writing code

Four of these are account administration, not engineering, and two of them **hard-block Milestone 3**. Start them in hour one; they run in parallel with M0 and M1.

- [ ] **GitHub App** registered, with exactly the permissions in [04-integrations.md](04-integrations.md) (Contents RW, Pull requests RW, Deployments R, Actions R, Checks R, Metadata R — and *nothing else*). Save the PEM base64-encoded.
- [ ] **Demo repo** created and pushed, containing a real `config/database.yml` (or equivalent) with `DB_POOL_SIZE: 50` in it. This is the file the agent reverts. Without it there is no PR.
- [ ] **Branch protection on `main`**: require 1 approving review, require status checks, App **not** on the bypass list. Screenshot it — it is the concrete artefact behind the safety claim, and it is also the thing you will forget to configure before the demo.
- [ ] **Slack app** in a workspace you control, bot scopes `chat:write`, `chat:write.public`, `users:read`, `users:read.email`. Interactivity toggled on (URL comes later).
- [ ] **Tunnel** working: `cloudflared tunnel --url http://localhost:8000`. Verify GitHub can reach it with a ping event.
- [ ] **Anthropic API key** with a **spend cap set in the console**. Belt-and-braces alongside `HAALAND_LLM_MAX_USD_PER_INCIDENT`.

Everything else in `.env.example` can stay unset — the app should fail fast on missing *required* config only, so make the Jira/PagerDuty blocks optional from the start rather than commenting them out later.

---

## Build sequence — five milestones

Each milestone has a **gate you can actually run**. Do not start the next one until the gate passes.

### M0 — Walking skeleton (2 days)

Everything runs. Nothing is intelligent. Nothing is even correlated.

**Build**
- Monorepo per [07-directory-structure.md](07-directory-structure.md), trimmed to what exists.
- `docker-compose.yml`: postgres, redis, api, worker, 2 bank services, loadgen, prometheus, alertmanager, loki, tempo, otel-collector.
- Alembic `0001_core_schema` — the whole schema, including `incident_events` and its `BEFORE UPDATE OR DELETE` trigger.
- `POST /webhooks/alertmanager`: verify bearer → validate Pydantic → insert `signals` row → enqueue → `202`. No logic in the handler.
- `Makefile`: `up`, `seed`, `chaos-pool`, `reset`, `logs`.

**Gate**
```bash
make up && make seed
sleep 60                     # let baseline traffic accumulate
make chaos-pool
# within ~90s
psql -c "select source, summary, received_at from signals order by received_at desc limit 1;"
```

**Watch-outs**
- **Write the hash-chain canonicalisation test before you write anything that inserts an event.** `0001` is immutable by design — adding a column later changes hash inputs and invalidates every prior event's verification. Pin an RFC 8785 JCS implementation and assert a known payload → known digest. That single test is the regression net for the whole compliance claim.
- **Two forward references in the doc-03 DDL will fail if applied in order**: `signals.incident_id → incidents(id)` and `incidents.suspected_deployment_id → deployments(id)` are both declared before their target tables. Create the tables first and add those two FKs with `ALTER TABLE` at the end of the migration.
- **Create the extensions inside the migration**, not only in `infra/postgres/init.sql`. Doc 07 puts `pgcrypto`/`citext` in init.sql, but `testcontainers` spins a bare Postgres that never runs it — your DB tests will fail on `gen_random_uuid()` with a confusing error.

---

### M1 — Evidence pipeline, no AI at all (3 days)

This is the highest-leverage milestone and the one most likely to be skipped. Don't.

**Build**
- `IncidentService`: signal → incident, with Redis fingerprint dedupe.
- `AuditService`: chained append + `GET /api/incidents/{id}/audit/verify`.
- `EvidenceService`: `asyncio.gather` over Loki, Tempo, Prometheus, GitHub deploys.
  - **Loki adapter with error-signature grouping** — 500 lines → 5 signatures × 3 examples + counts.
  - **Tempo adapter with span-tree reduction** — top 20 spans by **self-time**, computed server-side.
- GitHub `push` / `deployment_status` webhooks mirroring into `deployments` with diff summaries.
- The deploy-correlation query (doc 03 — the deliberately simple one).
- Frontend: `/incidents` feed over SSE + `/incidents/[ref]` overview with the evidence accordion.

**Gate** — two parts, and the first matters more:

1. Dump the assembled evidence bundle to a JSON file and read it. **You must be able to diagnose the incident yourself, from that file alone, in ten seconds.** If you can't, no prompt will fix it — go back and improve the compression, not the model.
2. `make chaos-pool` → incident visible in the dashboard in <30s without a refresh; `/audit/verify` returns `{valid: true}` with ≥6 events.

**Watch-out** — resist adding the model here. Every hour you spend now making the bundle legible saves a day of prompt debugging in M2, because you will otherwise be unable to tell a bad diagnosis from a bad Loki query.

---

### M2 — Redaction boundary + two model calls (3 days)

**Build**
- `Redactor`: Presidio + banking recognisers + Luhn/mod-97 validators + the deterministic regex pre-pass. Union the results.
- AES-GCM token vault in Redis, 24h TTL; `redaction_maps` stores **counts only**.
- **The canary suite, wired into CI as a blocking check, on day one of this milestone** — not at the end.
- LLM client: usage capture, retries, refusal handling, per-incident budget enforcement, prompt loading + hashing.
- `Classification` and `Diagnosis` calls with structured output. Tier-1 floor and low-confidence escalation applied **in code, after parsing**.
- `ai_analyses` rows with model, prompt version, prompt hash, tokens, cache hits, cost, latency.
- Frontend: root cause card with confidence bar, `RedactedValue` masked chips, cost badge.

**Gate**
1. `grep` every recorded LLM request payload for each canary value → **zero hits**.
2. `make chaos-pool` → P1, confidence > 0.7, root cause names `DB_POOL_SIZE` and the correct commit SHA.
3. `cache_read_input_tokens > 0` on the second incident. If it is 0, something volatile leaked into your system prefix — fix it now, it will not fix itself.

**Watch-out** — over-redaction is the failure mode that kills diagnosis quality. If you tokenise every 16-digit number you tokenise the trace ID. The Luhn and mod-97 validators are not optional polish; they are what keeps the bundle diagnosable.

---

### M3 — The approval gate (4 days) ← this is the product

**Build**
- LangGraph graph with `AsyncPostgresSaver`, `thread_id = incident_id`.
- `interrupt()` at `request_approval` and `await_merge`.
- **Deterministic revert path**: you already know `previous_sha` from `deployments`. Generate the patch in code; use the model only for the PR narrative. This eliminates an entire class of malformed-diff failures.
- Post-parse remediation validation: path denylist, no `..`, 10-file ceiling. A policy rejection emits an audit event and pages — it is a security signal, not a retry.
- GitHub branch → commit → PR, labelled `incident`/`automated`/`needs-review`.
- Slack Block Kit approval card with the `confirm` dialog; `/webhooks/slack/interactions` with v0 signature verification, 5-minute replay window, **and a role check** (`approver` or `admin` — a valid Slack signature proves the request came from Slack, not that this person may authorise a rollback).
- Frontend: `/remediation` tab with diff viewer and approval panel, mandatory reject reason.

**Gate** — the single most important test in the project:
```bash
make chaos-pool                                    # wait for the Slack card
docker compose kill worker && docker compose up -d worker
# now click Approve in Slack
```
The graph must resume at exactly the right node. Also verify: the PR exists; attempting to merge as the App fails on branch protection; the audit chain contains `approval.granted` with the correct human actor label.

**Watch-out** — keep the graph nodes at 10–30 lines. A node unpacks state, calls one or two service methods, returns a patch. Business logic inside a node is logic you cannot unit-test without spinning a graph, and it is what makes the eventual Temporal migration a rewrite instead of a port.

---

### M4 — Document (3 days)

**Build**
- `verify_recovery`: poll Prometheus every 30s for up to 10 minutes, require 3 consecutive healthy samples.
- Post-mortem assembly: Jinja template driven by `incident_events`; the model writes **prose only** and is instructed not to touch the timeline table.
- Markdown + PDF export via WeasyPrint.
- Frontend: `/timeline` tab with the **chain integrity banner**, actor-type icons and filtering; post-mortem view with export.

**Gate**
1. Cold-start full run produces a post-mortem whose timeline table matches `incident_events` exactly, with no manual editing.
2. Tamper test: `ALTER TABLE incident_events DISABLE TRIGGER trg_events_append_only`, mutate one row, re-enable — the banner must render red at the **correct sequence number**.
3. PDF opens and is legible.

**End of M4 = the demo in [10-demo-script.md](10-demo-script.md) runs start to finish**, minus Beat 5's regression-test coda.

---

## The first three commits

Concrete enough to start on right now.

1. **`chore: monorepo scaffolding + compose`** — directory tree, `apps/api` with `uv` + FastAPI health endpoint, `apps/web` with Next.js + Tailwind + shadcn init, `docker-compose.yml` bringing up postgres + redis + api only. `make up` works.
2. **`feat: core schema + append-only audit chain`** — Alembic `0001` (extensions, all enums, all tables, the immutability trigger), `AuditService.append()` with JCS canonicalisation, and `tests/unit/test_hash_chain.py` asserting the known-payload → known-digest vector plus a test that `UPDATE` on `incident_events` raises.
3. **`feat: alertmanager webhook + signal persistence`** — bearer verification in `api/webhooks/signature.py`, Pydantic v4 payload model, `signals` insert, ARQ enqueue, `202`. Plus `tests/fixtures/webhooks/alertmanager_firing.json` and `scripts/replay_webhook.py`, which you will use dozens of times a day for the rest of the project.

---

## Decisions worth making before day 3

| Decision | Recommendation |
|---|---|
| Compose Postgres vs managed (Supabase/Neon) | **Compose.** Offline demo reliability beats zero-ops here, and nothing in the schema is self-host-specific if you change your mind. |
| Demo repo: personal account vs org | **Org**, even a throwaway one. Branch protection on free personal repos has had gaps; the protection screenshot is part of the deliverable. |
| Bank services in the same repo vs separate | **Same repo, `demo/services/`.** One `git clone && docker compose up` is worth more than purity. The *seed repo the agent PRs against* is separate and must be a real GitHub repo. |
| Ship the LangGraph port at M3, or use it from M0 | **M3.** Build M1–M2 as plain async service calls — faster to debug, and the node functions port over almost unchanged. Adding the graph earlier means debugging graph state while you are still debugging LogQL. |

---

## Corrections to fold into docs 00–10

Four things worth updating before you write code against them:

1. **`max_tokens` on `claude-opus-5` caps thinking *plus* response text**, and thinking is on by default (omitting the parameter runs adaptive). Doc 05's classify call at `max_tokens=4000` is tight once adaptive thinking is spending from the same budget — give it headroom or you will get truncation that looks like a parsing bug.
2. **Effort levels.** Doc 05 uses `high` for diagnose and `medium` for classify. Current guidance for Opus 5: `xhigh` is the best setting for coding/agentic work — use it for **remediation drafting**, which is code generation against a real diff. Conversely `low`/`medium` are unusually strong on this model, so sweep downward on your own evals rather than assuming higher is better.
3. **Handle safety refusals with a fallback, not just a branch.** Doc 05 correctly says to check `stop_reason == "refusal"` before reading `.content`. Worth adding: Opus 5 ships elevated cybersecurity safeguards, and an incident-response agent reading logs about auth failures, cert expiry and injected instructions is exactly the shape that can trip a cyber classifier on a *benign* request. Opt into server-side fallbacks so a decline is rescued rather than surfaced — verify the exact call shape against the installed SDK, since you are using `messages.parse()` for structured output rather than plain `create()`.
4. **Cost model is currently conservative.** `claude-sonnet-5` is on introductory pricing ($2/$10 per MTok) through 2026-08-31, so the post-mortem stage is cheaper than doc 05's table states until then. The ~$0.61-per-incident figure holds as an upper bound.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Tempo search returns nothing / flakes** | High | Have the Jaeger all-in-one swap ready — same OTLP ingest, simpler query API, one class in `TraceSource`. Decide by end of M1, not during the demo. |
| **Evidence bundle is too noisy to diagnose** | High | The M1 gate exists precisely to catch this. Do not proceed to M2 on a bundle you can't read yourself. |
| **Prompt cache never hits** (`cache_read_input_tokens = 0`) | Medium | Assert on it in the M2 gate. Cause is almost always a timestamp, incident ID, or unsorted JSON that leaked into the system prefix. |
| **Slack/GitHub webhook signature mismatch** | Medium | Always verify against `await request.body()` raw bytes, before any JSON parsing. One module, `api/webhooks/signature.py`, owns all of it. `replay_webhook.py` lets you debug this without triggering real events. |
| **The graph doesn't resume after restart** | Medium | It is the M3 gate. Test it on day 1 of M3 with a stub graph, not on day 4 with the real one. |
| **Chaos isn't reproducible on stage** | Medium | `make reset` between every rehearsal, and `for: 1m` on alert rules (never `0s`). Keep a completed incident at a known URL as the live fallback. |
| **Scope creep back into the cut list** | High | The cuts above are the plan. Re-read doc 08's cut lines before adding anything: never cut the redaction boundary, the audit chain, or the approval gate — and never *add* ahead of them. |

---

## Timeline summary

| Milestone | Days | Cumulative | Demonstrable at the end |
|---|---|---|---|
| Day 0 (parallel) | 0.5 | — | Nothing, but M3 is unblocked |
| M0 Walking skeleton | 2 | 2 | A fault produces a row in the database |
| M1 Evidence, no AI | 3 | 5 | A dashboard showing correlated evidence and a verified audit chain |
| M2 Redaction + diagnosis | 3 | 8 | A correct root cause with zero PII leakage |
| M3 The approval gate | 4 | 12 | **The product** — PR, Slack card, durable suspension |
| M4 Document | 3 | 15 | The full 5-minute demo |

Fifteen focused days, solo. Add ~40% if this is nights-and-weekends work, and re-order nothing — the sequence is load-bearing.
