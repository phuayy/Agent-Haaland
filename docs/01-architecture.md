# 01 — Architecture

## Design stance

Three decisions shape everything else:

1. **Event-sourced incidents.** The `incident_events` table is append-only and hash-chained. Current incident state is a projection over it. This costs a little query complexity and buys the compliance story for free — you cannot produce a tamper-evident audit trail by writing an audit log *alongside* mutable state, because the two can diverge.

2. **The orchestrator is a durable state machine, not a chat loop.** Incident response has hard human-approval gates that can last hours. A conversational agent loop cannot survive a backend redeploy mid-incident. A checkpointed graph can — it suspends, persists, and resumes.

3. **Adapters at every boundary.** `SignalSource`, `LogSource`, `TraceSource`, `SCMProvider`, `Notifier`, `TicketProvider`. The diagnosis engine talks to interfaces. Swapping Prometheus for Datadog is a config change plus one class.

---

## System component diagram

```mermaid
graph TB
    subgraph OBS["Observability Plane — Docker Compose"]
        PROM["Prometheus<br/>metrics + alert rules"]
        AM["Alertmanager<br/>routing + webhook"]
        LOKI["Loki<br/>logs"]
        TEMPO["Tempo<br/>traces"]
        OTEL["OTel Collector"]
    end

    subgraph SVC["Demo Banking Estate"]
        GW["api-gateway"]
        PAY["payments-api"]
        LED["ledger-service"]
        AUTH["auth-service"]
        NOTI["notification-worker"]
        PG1[("customer-db")]
    end

    subgraph EXT["External SaaS"]
        GH["GitHub App<br/>repos + PRs"]
        SLACK["Slack<br/>Bolt app"]
        JIRA["Jira Cloud"]
        PD["PagerDuty"]
        LLM["Claude API<br/>claude-opus-5"]
    end

    subgraph BE["Agent Haaland Backend — FastAPI"]
        WH["/webhooks/*<br/>signature verified"]
        ING["Ingestion + dedupe<br/>+ correlation"]
        ORCH["LangGraph orchestrator<br/>Postgres checkpointer"]
        RED["Redaction service<br/>Presidio + token vault"]
        EVID["Evidence collector"]
        REM["Remediation drafter"]
        DOC["Report generator"]
        API["REST + SSE API"]
    end

    subgraph DATA["State"]
        PG[("Postgres 16<br/>incidents, events,<br/>evidence, approvals")]
        REDIS[("Redis<br/>queue, dedupe,<br/>PII vault, cache")]
        S3[("Object store<br/>artifacts, PDFs")]
    end

    subgraph FE["Frontend — Next.js 15"]
        DASH["Dashboard"]
        DET["Incident detail<br/>+ trace map"]
        TL["Timeline / audit"]
        APR["Approval console"]
    end

    SVC -->|OTLP| OTEL
    OTEL --> TEMPO
    OTEL --> LOKI
    SVC -->|/metrics| PROM
    PROM --> AM
    AM -->|POST alert| WH
    GH -->|push, deployment_status| WH
    SLACK -->|interaction payload| WH

    WH --> ING --> ORCH
    ORCH <--> RED
    ORCH --> EVID
    EVID -.query.-> LOKI
    EVID -.query.-> TEMPO
    EVID -.query.-> GH
    RED -->|redacted bundle| LLM
    LLM -->|structured JSON| ORCH
    ORCH --> REM --> GH
    ORCH --> SLACK
    ORCH --> JIRA
    ORCH --> PD
    ORCH --> DOC --> S3

    ORCH <--> PG
    ORCH <--> REDIS
    API --> PG
    FE <-->|REST + SSE| API
```

---

## End-to-end incident workflow

This is the diagram to put on a slide.

```mermaid
flowchart TD
    A0["Fault injected / real degradation"] --> A1

    subgraph S1["STAGE 1 — DETECT"]
        A1["Prometheus rule fires<br/>latency p99 or error rate"]
        A2["Alertmanager POSTs webhook"]
        A3{"Fingerprint seen<br/>in dedupe window?"}
        A4["Attach to existing incident"]
        A5["Create incident<br/>status = detected"]
        A6["Collect evidence in parallel"]
        A6a["Loki: error logs<br/>t-15m to now"]
        A6b["Tempo: exemplar trace<br/>+ span timings"]
        A6c["GitHub: deploys, diffs,<br/>config changes t-2h"]
        A6d["Registry: downstream<br/>dependency graph"]
        A1 --> A2 --> A3
        A3 -->|yes| A4
        A3 -->|no| A5 --> A6
        A6 --> A6a & A6b & A6c & A6d
    end

    A6a & A6b & A6c & A6d --> B1

    subgraph S2["STAGE 2 — SAFE TRIAGE"]
        B1["Build evidence bundle"]
        B2["PII redaction<br/>Presidio + custom recognisers"]
        B3["Token vault write<br/>Redis, encrypted, 24h TTL"]
        B4["Claude call 1: classify<br/>structured output, P1..P4"]
        B5{"Severity?"}
        B6["Claude call 2: root cause<br/>with evidence citations"]
        B1 --> B2 --> B3 --> B4 --> B5
        B5 -->|P3 / P4| C_LOW
        B5 -->|P1 / P2| B6
    end

    C_LOW["Create Jira ticket<br/>attach evidence<br/>status = triaged_low"] --> Z1

    B6 --> C1

    subgraph S3["STAGE 3 — HUMAN IN THE LOOP"]
        C1["Page on-call via PagerDuty"]
        C2["Claude call 3: draft remediation<br/>revert or config restore"]
        C3["Create branch + PR<br/>App has NO merge scope"]
        C4["Post Slack card:<br/>evidence, diff, approve/reject"]
        C5(["GRAPH SUSPENDS<br/>checkpoint persisted"])
        C6{"Human decision"}
        C1 --> C2 --> C3 --> C4 --> C5 --> C6
    end

    C6 -->|reject / edit| D_REJ["Record rejection + reason<br/>await new instruction"]
    C6 -->|timeout 30m| D_ESC["Escalate to secondary on-call"]
    C6 -->|approve| D1

    D_ESC --> C6
    D_REJ --> Z1

    subgraph S4["STAGE 4 — DOCUMENT"]
        D1["Engineer merges PR<br/>CI deploys"]
        D2["Watch metrics for recovery<br/>SLO back under threshold"]
        D3["Claude call 4: generate<br/>regression test from failure"]
        D4["Open test PR"]
        D5["Assemble post-mortem<br/>from event timeline"]
        D6["Render Markdown + PDF<br/>store artifact"]
        D1 --> D2 --> D3 --> D4 --> D5 --> D6
    end

    D6 --> Z1["Incident closed<br/>hash chain sealed"]

    Z1 --> Z2["Compliance export available"]
```

---

## Incident state machine

Every transition writes an `incident_events` row. Illegal transitions are rejected at the service layer, not just discouraged.

```mermaid
stateDiagram-v2
    [*] --> detected: alert webhook

    detected --> enriching: evidence collection starts
    enriching --> triaging: bundle redacted and sent
    enriching --> failed: evidence collection error

    triaging --> triaged_low: severity P3 or P4
    triaging --> diagnosing: severity P1 or P2

    triaged_low --> closed: Jira ticket filed

    diagnosing --> awaiting_approval: PR drafted, Slack posted
    diagnosing --> failed: no confident root cause

    awaiting_approval --> approved: human approves
    awaiting_approval --> rejected: human rejects
    awaiting_approval --> escalated: 30m timeout
    escalated --> awaiting_approval: secondary paged

    rejected --> diagnosing: re-draft with human feedback
    rejected --> closed: human takes over manually

    approved --> remediating: PR merged, deploy running
    remediating --> verifying: deploy complete
    verifying --> remediating: SLO still breached, retry
    verifying --> documenting: SLO recovered

    documenting --> closed: post-mortem generated

    failed --> closed: manual close with reason
    closed --> [*]
```

---

## Sequence: alert to pending pull request

```mermaid
sequenceDiagram
    autonumber
    participant AM as Alertmanager
    participant API as FastAPI
    participant Q as Redis queue
    participant W as Worker
    participant LK as Loki / Tempo
    participant GH as GitHub
    participant R as Redactor
    participant CL as Claude
    participant DB as Postgres
    participant SL as Slack

    AM->>API: POST /webhooks/alertmanager
    API->>API: verify shared secret, validate schema
    API->>DB: INSERT signal (raw payload)
    API->>Q: enqueue triage job
    API-->>AM: 202 Accepted

    W->>Q: dequeue
    W->>DB: create incident + event(detected)

    par Evidence collection
        W->>LK: LogQL query, window t-15m
        W->>LK: TraceQL query for exemplar
    and
        W->>GH: GET deployments, commits, diffs
    end
    LK-->>W: log lines + spans
    GH-->>W: deploy list + diff hunks
    W->>DB: INSERT evidence rows + event(enriched)

    W->>R: redact(bundle)
    R->>R: Presidio analyze + custom recognisers
    R-->>W: redacted bundle + vault_id
    Note over R: real values encrypted in Redis<br/>never leave the boundary

    W->>CL: classify(bundle) — structured output
    CL-->>W: {severity: P1, confidence: 0.91, rationale}
    W->>DB: event(triaged, model, tokens, cost)

    W->>CL: diagnose(bundle) — structured output
    CL-->>W: {root_cause, evidence_refs[], fix_strategy}
    W->>DB: event(diagnosed)

    W->>CL: draft_fix(root_cause, diff) — structured output
    CL-->>W: {files[], patch, pr_title, pr_body}
    W->>GH: create branch + commit + open PR
    GH-->>W: pr_url (state: open, not mergeable by app)
    W->>DB: INSERT remediation(status=pending) + event

    W->>SL: chat.postMessage — Block Kit approval card
    SL-->>W: message_ts
    W->>DB: event(approval_requested)
    Note over W,DB: LangGraph checkpoint written.<br/>Graph suspends here indefinitely.
```

---

## Sequence: human approval resumes the graph

```mermaid
sequenceDiagram
    autonumber
    participant Eng as On-call engineer
    participant SL as Slack
    participant API as FastAPI
    participant DB as Postgres
    participant W as Worker
    participant GH as GitHub
    participant PROM as Prometheus

    Eng->>SL: clicks "Approve rollback"
    SL->>API: POST /webhooks/slack/interactions
    API->>API: verify v0 HMAC + 5-min timestamp window
    API->>DB: INSERT approval(actor, decision, ts)
    API->>DB: event(approved) — hash chained
    API-->>SL: 200 + ephemeral ack
    API->>W: resume(thread_id=incident_id)

    W->>SL: update card to "Approved by @eng — merging"
    Note over W,GH: App still cannot merge.<br/>Engineer merges, or a<br/>separate scoped bot does.
    GH-->>API: webhook pull_request.closed merged=true
    API->>DB: event(pr_merged)
    API->>W: resume(verify)

    loop poll up to 10 min
        W->>PROM: query SLO metric
        PROM-->>W: current p99
    end
    W->>DB: event(recovered)
    W->>W: generate regression test, open test PR
    W->>W: assemble post-mortem from event timeline
    W->>DB: event(closed) — chain sealed
```

---

## Deployment topology

For the prototype, one machine, one `docker compose up`.

```mermaid
graph LR
    subgraph HOST["Developer machine / single VM"]
        subgraph NET1["haaland-net"]
            WEB["web :3000<br/>Next.js"]
            APIC["api :8000<br/>FastAPI + uvicorn"]
            WORK["worker<br/>ARQ consumer"]
            PGC[("postgres :5432")]
            RDC[("redis :6379")]
        end
        subgraph NET2["obs-net"]
            PROMC["prometheus :9090"]
            AMC["alertmanager :9093"]
            LOKIC["loki :3100"]
            TEMPOC["tempo :3200"]
            OTELC["otel-collector :4317"]
            GRAF["grafana :3001 (optional)"]
        end
        subgraph NET3["bank-net"]
            S1["api-gateway :8081"]
            S2["payments-api :8082"]
            S3["ledger-service :8083"]
            S4["auth-service :8084"]
            S5["notification-worker"]
            S6[("bank-postgres")]
        end
    end
    TUN["ngrok / cloudflared tunnel"] --> APIC
    GHX["GitHub"] --> TUN
    SLX["Slack"] --> TUN
```

A public tunnel is required only because GitHub and Slack must reach the webhook endpoints. Alertmanager talks to the API over the internal Docker network.

## Why a worker process at all

The alert webhook must return `202` in well under a second — Alertmanager retries aggressively and a slow endpoint causes duplicate alerts. Evidence collection plus three or four LLM calls takes 20–90 seconds. So the HTTP handler does exactly three things: verify, persist the raw signal, enqueue. Everything else happens in the worker.

This also means a backend restart mid-incident loses nothing: the job is in Redis, the graph checkpoint is in Postgres.
