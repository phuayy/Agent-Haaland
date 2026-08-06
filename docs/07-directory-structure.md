# 07 — Directory Structure

## Monorepo, one repository

Backend (Python) and frontend (TypeScript) in one repo. Rationale: the OpenAPI-generated client means the two must be versioned together, and a demo you can `git clone && docker compose up` is worth more than architectural purity.

```
agent-haaland/
├── README.md
├── docker-compose.yml                # everything, one command
├── docker-compose.override.yml       # local dev: hot reload, exposed ports
├── Makefile                          # make up / seed / chaos / test / evals
├── .env.example
├── .gitignore
├── .python-version                   # 3.12
│
├── docs/                             # ← this plan
│   ├── README.md
│   ├── 00-overview.md
│   ├── 01-architecture.md
│   ├── 02-tech-stack.md
│   ├── 03-data-model.md
│   ├── 04-integrations.md
│   ├── 05-ai-pipeline.md
│   ├── 06-frontend.md
│   ├── 07-directory-structure.md
│   ├── 08-roadmap.md
│   ├── 09-security-compliance.md
│   ├── 10-demo-script.md
│   └── adr/                          # architecture decision records
│       ├── 0001-self-hosted-observability.md
│       ├── 0002-langgraph-over-raw-tool-loop.md
│       ├── 0003-append-only-hash-chained-audit.md
│       └── 0004-no-production-write-path.md
│
├── apps/
│   ├── api/                          # FastAPI backend
│   └── web/                          # Next.js frontend
│
├── infra/                            # observability + runtime config
├── demo/                             # fake banking estate + chaos
├── packages/                         # shared, generated artifacts
└── scripts/                          # dev ergonomics
```

---

## `apps/api` — the backend

```
apps/api/
├── pyproject.toml                    # uv-managed
├── uv.lock
├── Dockerfile
├── alembic.ini
│
├── prompts/                          # versioned prompt files, hashed at load
│   ├── system/
│   │   ├── base.md
│   │   └── service_registry.md.j2
│   ├── classify/instructions.md
│   ├── diagnose/instructions.md
│   ├── remediate/instructions.md
│   ├── test/instructions.md
│   └── report/instructions.md
│
├── templates/                        # Jinja2 output templates
│   ├── pr_body.md.j2
│   ├── postmortem.md.j2
│   ├── postmortem.html.j2            # for the PDF renderer
│   └── jira_description.json.j2      # Atlassian Document Format
│
├── seeds/
│   ├── services.yaml                 # the service registry
│   ├── dependencies.yaml
│   └── users.yaml
│
├── migrations/                       # Alembic
│   ├── env.py
│   └── versions/
│       ├── 0001_core_schema.py       # incident_events + trigger live here forever
│       └── ...
│
├── evals/
│   ├── run_evals.py
│   ├── report.py                     # renders the PR comparison table
│   └── scenarios/
│       ├── bad_deploy_pool_size/{bundle.json,expected.json}
│       ├── downstream_timeout_cascade/
│       ├── cert_expiry/
│       ├── memory_leak_slow_burn/
│       ├── flapping_alert_no_impact/
│       ├── prompt_injection_in_logs/
│       └── ...
│
├── tests/
│   ├── conftest.py                   # testcontainers Postgres + Redis
│   ├── fixtures/
│   │   ├── webhooks/                 # captured real payloads
│   │   │   ├── alertmanager_firing.json
│   │   │   ├── github_push.json
│   │   │   ├── github_deployment_status.json
│   │   │   └── slack_block_actions.json
│   │   └── llm/                      # recorded Claude responses
│   ├── unit/
│   ├── integration/
│   └── redaction/
│       └── test_no_leakage.py        # the canary suite
│
└── src/haaland/
    ├── __init__.py
    ├── main.py                       # FastAPI app factory
    ├── worker.py                     # ARQ worker entrypoint
    ├── config.py                     # pydantic-settings, fails fast
    ├── deps.py                       # DI container
    ├── logging.py                    # structlog config
    │
    ├── api/                          # HTTP layer — thin, no logic
    │   ├── router.py
    │   ├── deps.py                   # current_user, require_role
    │   ├── routes/
    │   │   ├── incidents.py
    │   │   ├── evidence.py
    │   │   ├── remediations.py
    │   │   ├── approvals.py
    │   │   ├── audit.py              # includes /verify
    │   │   ├── services.py
    │   │   ├── analytics.py
    │   │   ├── postmortems.py
    │   │   └── stream.py             # SSE
    │   ├── webhooks/                 # verify → validate → persist → enqueue
    │   │   ├── alertmanager.py
    │   │   ├── github.py
    │   │   ├── slack.py
    │   │   ├── sentry.py
    │   │   └── signature.py          # all HMAC verification, one place
    │   └── schemas/                  # request/response DTOs (≠ domain models)
    │
    ├── domain/                       # pure — no I/O, no framework imports
    │   ├── models.py                 # Incident, Signal, Evidence, ...
    │   ├── enums.py
    │   ├── events.py                 # event type constants + payload schemas
    │   ├── state_machine.py          # legal transitions, enforced
    │   └── errors.py
    │
    ├── db/
    │   ├── session.py
    │   ├── base.py
    │   ├── models/                   # SQLAlchemy ORM
    │   │   ├── incident.py
    │   │   ├── incident_event.py
    │   │   ├── evidence.py
    │   │   ├── deployment.py
    │   │   ├── ai_analysis.py
    │   │   ├── remediation.py
    │   │   ├── approval.py
    │   │   └── service.py
    │   └── repositories/             # query objects; services depend on these
    │       ├── incidents.py
    │       ├── events.py             # append() computes the hash chain
    │       ├── evidence.py
    │       └── deployments.py
    │
    ├── services/                     # business logic — framework-free
    │   ├── incident_service.py       # create, transition, correlate
    │   ├── audit_service.py          # append, canonicalise, verify chain
    │   ├── correlation_service.py    # signal → incident, deploy → incident
    │   ├── evidence_service.py       # parallel fan-out collection
    │   ├── triage_service.py
    │   ├── remediation_service.py    # patch validation, path denylist
    │   ├── notification_service.py
    │   ├── postmortem_service.py
    │   └── cost_service.py           # budget enforcement
    │
    ├── agent/                        # LangGraph — orchestration only
    │   ├── graph.py                  # the compiled state machine
    │   ├── state.py                  # IncidentState TypedDict
    │   ├── nodes/
    │   │   ├── collect_evidence.py
    │   │   ├── redact.py
    │   │   ├── classify.py
    │   │   ├── diagnose.py
    │   │   ├── draft_remediation.py
    │   │   ├── open_pr.py
    │   │   ├── request_approval.py   # interrupt()
    │   │   ├── await_merge.py        # interrupt()
    │   │   ├── verify_recovery.py
    │   │   ├── generate_test.py
    │   │   └── generate_report.py
    │   ├── routing.py                # conditional edge functions
    │   └── checkpointer.py
    │
    ├── llm/
    │   ├── client.py                 # AsyncAnthropic wrapper, retries, usage capture
    │   ├── prompts.py                # load + hash + version prompt files
    │   ├── schemas.py                # Classification, Diagnosis, RemediationDraft, ...
    │   ├── rendering.py              # evidence bundle → prompt text
    │   ├── budget.py                 # per-incident + daily USD ceiling
    │   └── fake.py                   # FakeLLM for tests and evals
    │
    ├── redaction/
    │   ├── service.py                # Redactor
    │   ├── recognizers.py            # banking-specific Presidio recognisers
    │   ├── validators.py             # Luhn, IBAN mod-97
    │   ├── vault.py                  # AES-GCM Redis token vault
    │   └── prefilter.py              # deterministic regex pass
    │
    ├── integrations/
    │   ├── base.py                   # the Protocols
    │   ├── registry.py               # config-driven adapter selection
    │   ├── observability/
    │   │   ├── alertmanager.py
    │   │   ├── prometheus.py
    │   │   ├── loki.py               # includes log signature grouping
    │   │   ├── tempo.py              # includes span-tree reduction
    │   │   ├── sentry.py
    │   │   └── datadog.py            # Phase 5
    │   ├── scm/
    │   │   ├── github.py             # githubkit App auth, branch/commit/PR
    │   │   └── diff.py               # diff summarisation for the prompt
    │   ├── notify/
    │   │   ├── slack.py
    │   │   ├── blocks.py             # Block Kit builders
    │   │   └── pagerduty.py
    │   └── tickets/
    │       ├── jira.py
    │       ├── adf.py                # Atlassian Document Format helper
    │       └── linear.py
    │
    └── tasks/                        # ARQ job definitions
        ├── triage.py
        ├── enrich.py
        ├── verify.py
        └── cleanup.py                # vault expiry, raw payload nulling
```

### Why this layering

`api/` → `services/` → `db/repositories/`, with `domain/` at the bottom importing nothing.

The rule that keeps it honest: **`services/` may not import `fastapi`, `langgraph`, or any vendor SDK.** It imports Protocols from `integrations/base.py`. Enforce it with an import-linter rule in CI. This is what makes the Temporal migration (Phase 6) a rewrite of `agent/graph.py` and nothing else.

`agent/nodes/*` are thin — each node is 10–30 lines that unpacks state, calls one or two service methods, and returns a state patch. Business logic in a graph node is business logic you cannot unit test without a graph.

---

## `apps/web` — the frontend

```
apps/web/
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── components.json                   # shadcn/ui config
├── Dockerfile
│
└── src/
    ├── app/
    │   ├── layout.tsx
    │   ├── globals.css
    │   ├── page.tsx                  # → /incidents
    │   ├── incidents/
    │   │   ├── page.tsx              # feed (server component, first page SSR'd)
    │   │   └── [reference]/
    │   │       ├── layout.tsx        # tabs + header + SSE subscription
    │   │       ├── page.tsx          # overview
    │   │       ├── trace/page.tsx
    │   │       ├── timeline/page.tsx
    │   │       ├── remediation/page.tsx
    │   │       └── postmortem/page.tsx
    │   ├── services/
    │   │   ├── page.tsx
    │   │   └── [name]/page.tsx
    │   ├── analytics/page.tsx
    │   ├── settings/
    │   │   ├── integrations/page.tsx
    │   │   ├── prompts/page.tsx
    │   │   └── users/page.tsx
    │   └── api/
    │       ├── [...proxy]/route.ts   # proxy to FastAPI, attaches session
    │       └── stream/[...path]/route.ts
    │
    ├── components/
    │   ├── ui/                       # shadcn primitives (vendored)
    │   ├── incident/
    │   │   ├── incident-list.tsx
    │   │   ├── incident-row.tsx
    │   │   ├── severity-badge.tsx
    │   │   ├── status-badge.tsx
    │   │   ├── root-cause-card.tsx
    │   │   ├── evidence-accordion.tsx
    │   │   ├── ai-reasoning-disclosure.tsx
    │   │   ├── cost-badge.tsx
    │   │   └── redacted-value.tsx
    │   ├── trace/
    │   │   ├── service-map.tsx
    │   │   ├── service-node.tsx
    │   │   ├── span-waterfall.tsx
    │   │   └── layout.ts             # dagre
    │   ├── audit/
    │   │   ├── audit-timeline.tsx
    │   │   ├── timeline-entry.tsx
    │   │   └── chain-integrity-banner.tsx
    │   ├── remediation/
    │   │   ├── diff-viewer.tsx
    │   │   └── approval-panel.tsx
    │   └── analytics/
    │       ├── metric-card.tsx
    │       └── ai-accuracy-panel.tsx
    │
    ├── hooks/
    │   ├── use-incident-stream.ts
    │   ├── use-incidents.ts
    │   └── use-approval.ts
    │
    ├── lib/
    │   ├── api/
    │   │   ├── schema.d.ts           # GENERATED — do not edit
    │   │   └── client.ts             # openapi-fetch instance
    │   ├── severity.ts               # colour/label maps, single source
    │   ├── time.ts                   # absolute + relative formatting
    │   └── utils.ts
    │
    └── types/
        └── domain.ts                 # narrowed aliases over generated schema
```

---

## `infra` — the observability plane

```
infra/
├── prometheus/
│   ├── prometheus.yml                # scrape configs, alertmanager target
│   └── rules/
│       └── banking.yml               # the alert rules that drive the demo
├── alertmanager/
│   └── alertmanager.yml              # webhook receiver → api:8000
├── loki/
│   └── loki-config.yml
├── tempo/
│   └── tempo-config.yml
├── otel/
│   └── otel-collector-config.yml     # OTLP in → Tempo + Loki out
├── grafana/                          # optional, for our own debugging
│   ├── datasources.yml
│   └── dashboards/
└── postgres/
    └── init.sql                      # extensions: pgcrypto, citext, vector
```

Alertmanager config is the load-bearing file:

```yaml
route:
  receiver: agent-haaland
  group_by: [alertname, service]
  group_wait: 10s
  group_interval: 30s
  repeat_interval: 4h

receivers:
  - name: agent-haaland
    webhook_configs:
      - url: http://api:8000/webhooks/alertmanager
        send_resolved: true
        http_config:
          authorization:
            type: Bearer
            credentials_file: /etc/alertmanager/webhook_token
```

---

## `demo` — the breakable banking estate

```
demo/
├── services/
│   ├── _shared/
│   │   ├── telemetry.py              # OTel + Prometheus setup, imported by all
│   │   ├── chaos.py                  # the /chaos admin router
│   │   └── pii.py                    # generates realistic fake PII into logs
│   ├── api-gateway/{app.py,Dockerfile,pyproject.toml}
│   ├── payments-api/
│   ├── ledger-service/
│   ├── auth-service/
│   └── notification-worker/
├── loadgen/
│   └── traffic.py                    # steady baseline so metrics exist
├── chaos/
│   ├── break_pool_size.sh            # the headline demo fault
│   ├── inject_latency.sh
│   ├── kill_service.sh
│   ├── expire_cert.sh
│   └── reset.sh                      # returns everything to healthy
└── seed_repo/                        # a real Git repo the agent can PR against
    └── README.md
```

`seed_repo` matters: the demo needs an actual GitHub repository whose `config/database.yml` the agent can revert. Committing a template here plus a `scripts/bootstrap_demo_repo.sh` that pushes it makes the demo reproducible on a fresh machine.

---

## `packages` and `scripts`

```
packages/
└── api-types/                        # generated OpenAPI types, if extracted
                                      # for reuse; otherwise lives in apps/web

scripts/
├── bootstrap.sh                      # uv sync, pnpm install, migrate, seed
├── seed_db.py
├── replay_webhook.py                 # POST a fixture with a valid signature
├── bootstrap_demo_repo.sh
├── verify_chain.py                   # CLI audit verification
└── record_llm_fixtures.py            # capture real responses for the eval suite
```

## `Makefile` — the interface everyone actually uses

```make
up:        ## bring up the whole stack
	docker compose up -d --build

seed:      ## migrate + seed services, users, demo repo
	docker compose exec api alembic upgrade head
	docker compose exec api python -m scripts.seed_db

chaos-pool: ## trigger the headline demo incident
	./demo/chaos/break_pool_size.sh

reset:     ## return the estate to healthy
	./demo/chaos/reset.sh

test:
	docker compose exec api pytest -q

evals:     ## run the golden-scenario suite
	docker compose exec api python -m evals.run_evals

gen-api:   ## regenerate the frontend client from OpenAPI
	cd apps/web && pnpm gen:api

logs:
	docker compose logs -f api worker
```
