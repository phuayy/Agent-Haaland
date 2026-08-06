# 04 — Integrations & Webhook Contracts

Every integration sits behind a Protocol. The orchestrator imports the Protocol, never the vendor SDK.

```
SignalSource   → AlertmanagerSource | SentrySource | DatadogSource | GrafanaSource
LogSource      → LokiSource | DatadogLogSource
TraceSource    → TempoSource | JaegerSource | DatadogAPMSource
MetricSource   → PrometheusSource | DatadogMetricSource
SCMProvider    → GitHubProvider | GitLabProvider
Notifier       → SlackNotifier | PagerDutyNotifier | TeamsNotifier
TicketProvider → JiraProvider | LinearProvider
```

---

## Inbound webhooks

All inbound endpoints follow the same five-step contract, in this order:

1. **Verify** signature or shared secret — before parsing the body.
2. **Validate** against a Pydantic model — reject unknown shapes.
3. **Persist** the raw payload.
4. **Enqueue** work.
5. **Return 2xx fast** — under 500 ms, always.

Never do work in the handler. Never return a 5xx for a business-logic problem — senders retry on 5xx and you will create duplicate incidents.

### `POST /webhooks/alertmanager`

Primary detection trigger.

**Auth:** `Authorization: Bearer <ALERTMANAGER_WEBHOOK_TOKEN>`, compared with `hmac.compare_digest`. Alertmanager supports this via `http_config.authorization` — do not use an unauthenticated endpoint even on a private network.

**Payload (Alertmanager v4):**

```json
{
  "version": "4",
  "groupKey": "{}:{alertname=\"HighLatency\"}",
  "status": "firing",
  "receiver": "agent-haaland",
  "groupLabels":  { "alertname": "HighLatency" },
  "commonLabels": { "service": "payments-api", "severity": "critical" },
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname": "HighLatency",
      "service": "payments-api",
      "severity": "critical",
      "namespace": "banking-prod"
    },
    "annotations": {
      "summary": "p99 latency 4.2s (threshold 500ms)",
      "runbook_url": "https://wiki/runbooks/payments-latency"
    },
    "startsAt": "2026-08-06T09:12:03.117Z",
    "endsAt": "0001-01-01T00:00:00Z",
    "generatorURL": "http://prometheus:9090/graph?...",
    "fingerprint": "a1b2c3d4e5f60718"
  }]
}
```

`fingerprint` is our idempotency key. Dedupe rule:

```python
key = f"dedupe:alertmanager:{fingerprint}"
if await redis.set(key, incident_id, ex=300, nx=True):
    # new -> create incident
else:
    # existing -> attach signal, emit alert.correlated, do not re-run triage
```

`status: "resolved"` closes the signal and, if it was the only signal on the incident and no remediation is pending, transitions the incident toward `verifying`.

**Alert rules that matter** (`infra/prometheus/rules/banking.yml`):

```yaml
groups:
  - name: banking-slo
    rules:
      - alert: HighLatency
        expr: |
          histogram_quantile(0.99,
            sum by (le, service) (rate(http_request_duration_seconds_bucket[2m]))
          ) > 0.5
        for: 1m
        labels: { severity: critical }
        annotations:
          summary: "{{ $labels.service }} p99 latency {{ $value | humanizeDuration }}"

      - alert: HighErrorRate
        expr: |
          sum by (service) (rate(http_requests_total{status=~"5.."}[2m]))
          / sum by (service) (rate(http_requests_total[2m])) > 0.05
        for: 1m
        labels: { severity: critical }

      - alert: DBConnectionPoolExhausted
        expr: db_connections_active / db_connections_max > 0.95
        for: 30s
        labels: { severity: critical }

      - alert: ServiceDown
        expr: up{job="banking-services"} == 0
        for: 30s
        labels: { severity: critical }
```

`for: 1m` matters for the demo — it makes the fire time predictable. Do not set it to `0s`; flapping alerts make a live demo look broken.

### `POST /webhooks/github`

**Auth:** `X-Hub-Signature-256` — HMAC-SHA256 of the raw body with the App's webhook secret. Compare with `hmac.compare_digest` against the *raw bytes*, before any JSON parsing.

**Events subscribed:**

| Event | What we do |
|---|---|
| `push` (to default branch) | Record a deployment candidate; fetch the compare diff |
| `deployment_status` | Mark deployment `success`/`failure`; if it succeeds during `remediating`, advance to `verifying` |
| `workflow_run` (completed) | Alternative deploy signal for repos using Actions-only deploys |
| `pull_request` (closed, merged) | If it matches a remediation → `pr.merged` event, resume the graph |
| `pull_request_review` | Record review as a secondary approval channel |

For a `push`, we immediately call `GET /repos/{owner}/{repo}/compare/{base}...{head}` and store a diff summary — file list, additions/deletions, and the actual hunks for files under a size threshold. That summary is what the model sees; we never paste an entire repository into a prompt.

### `POST /webhooks/slack/interactions`

**Auth:** Slack's v0 signing scheme.

```python
basestring = f"v0:{timestamp}:{raw_body.decode()}"
expected = "v0=" + hmac.new(signing_secret, basestring.encode(), sha256).hexdigest()
if abs(time.time() - int(timestamp)) > 300:   # replay window
    raise HTTPException(401)
if not hmac.compare_digest(expected, header_sig):
    raise HTTPException(401)
```

Body is `application/x-www-form-urlencoded` with a `payload` field containing JSON. The `action_id` carries our intent and the `value` carries the remediation id:

```json
{
  "type": "block_actions",
  "user": { "id": "U0123", "username": "priya" },
  "actions": [{ "action_id": "approve_remediation", "value": "<remediation_uuid>" }],
  "response_url": "https://hooks.slack.com/actions/...",
  "message": { "ts": "1754472723.001" }
}
```

Handler: resolve the Slack user to a `users` row (reject unknown users — do not create on the fly), insert an `approvals` row, emit `approval.granted`/`approval.denied`, ack within 3 seconds, then resume the graph asynchronously.

**Authorisation, not just authentication:** verify the resolved user has role `approver` or `admin`. A valid Slack signature proves the request came from Slack, not that this person may approve a production rollback.

### `POST /webhooks/sentry` (Phase 2)

Sentry Internal Integrations sign with `Sentry-Hook-Signature` (HMAC-SHA256 of the body with the client secret). Useful events: `error.created`, `issue.created`, `metric_alert.triggered`. Sentry's *suspect commits* field is an independent second opinion on which deploy caused the problem — worth surfacing next to our own correlation.

### `POST /webhooks/datadog` (Phase 5)

Datadog webhooks are user-templated, so we define the template ourselves and treat a shared secret header as auth. Because the payload shape is ours, `DatadogSource.parse` is trivial.

---

## Outbound integrations

### GitHub — the least-privilege core of the safety story

**Use a GitHub App, not a PAT.** A PAT carries a human's full permissions; an App installation carries exactly what you granted, per repository, with short-lived tokens.

Permissions granted:

| Permission | Level | Why |
|---|---|---|
| Contents | **Read & write** | Create the branch and commit the patch |
| Pull requests | **Read & write** | Open the PR, comment |
| Deployments | Read | Deploy history correlation |
| Actions | Read | Workflow run status |
| Metadata | Read | Required baseline |
| Checks | Read | CI status on the remediation PR |

Permissions deliberately **not** granted: Administration, Workflows (write), Environments, Secrets. And critically, **there is no "merge" permission to grant** — GitHub merge capability comes from Contents: write plus branch protection. So branch protection is the actual control:

- `main` requires ≥1 approving review from a **human** (`CODEOWNERS`).
- Require status checks to pass.
- **Do not** add the App to the bypass list.
- Enable "Dismiss stale reviews".

The result: even if the agent were fully compromised, the worst it can do is open a pull request. That is the sentence to put on the slide.

Auth flow with `githubkit`:

```python
from githubkit import GitHub, AppInstallationAuthStrategy

gh = GitHub(AppInstallationAuthStrategy(
    app_id=settings.github_app_id,
    private_key=settings.github_private_key,
    installation_id=settings.github_installation_id,
))
# githubkit handles JWT signing and installation-token refresh (1h expiry)
```

Remediation PR flow:

```
1. GET  /repos/{o}/{r}/git/ref/heads/{default}          -> base sha
2. POST /repos/{o}/{r}/git/refs                          -> haaland/INC-2026-0042-rollback
3. PUT  /repos/{o}/{r}/contents/{path}   (per file)      -> commit with the patch
4. POST /repos/{o}/{r}/pulls                             -> draft=false, open PR
5. POST /repos/{o}/{r}/issues/{n}/labels                 -> incident, automated, needs-review
6. POST /repos/{o}/{r}/issues/{n}/comments               -> evidence bundle as a comment
```

Branch naming is fixed at `haaland/{incident_reference}-{strategy}` so an operator can find, and delete, everything the agent ever created with one glob.

PR body template (`apps/api/templates/pr_body.md.j2`) always includes: incident reference and dashboard link, the AI-stated root cause, the evidence that supports it with links back to Loki/Tempo, the confidence score, a "this PR was drafted automatically and requires human review" banner, and a rollback-of-the-rollback instruction.

### Slack

Bot scopes: `chat:write`, `chat:write.public`, `channels:manage` (to open a per-incident channel), `users:read`, `users:read.email`, `reactions:write`.

Two message types:

**1. Incident alert (Block Kit)** — severity-coloured, with the evidence summary, trace map link, and the approval actions:

```json
{
  "blocks": [
    { "type": "header", "text": { "type": "plain_text", "text": "🔴 P1 — payments-api latency" } },
    { "type": "section", "fields": [
      { "type": "mrkdwn", "text": "*Incident*\nINC-2026-0042" },
      { "type": "mrkdwn", "text": "*Detected*\n<!date^1754472723^{time}|09:12>" },
      { "type": "mrkdwn", "text": "*Confidence*\n91%" },
      { "type": "mrkdwn", "text": "*Suspect deploy*\n<https://github.com/...|a3f91c2>" }
    ]},
    { "type": "section", "text": { "type": "mrkdwn",
      "text": "*Root cause*\nDeploy `a3f91c2` reduced `DB_POOL_SIZE` from 50 to 5. Pool saturated at 09:11:47; `ledger-service` began queueing, cascading to `payments-api`." }},
    { "type": "actions", "elements": [
      { "type": "button", "style": "primary", "text": { "type": "plain_text", "text": "Approve rollback" },
        "action_id": "approve_remediation", "value": "<uuid>",
        "confirm": { "title": {"type":"plain_text","text":"Approve production rollback?"},
                     "text": {"type":"mrkdwn","text":"This authorises merging PR #217 to `main`."},
                     "confirm": {"type":"plain_text","text":"Approve"},
                     "deny": {"type":"plain_text","text":"Cancel"} } },
      { "type": "button", "style": "danger", "text": { "type": "plain_text", "text": "Reject" },
        "action_id": "reject_remediation", "value": "<uuid>" },
      { "type": "button", "text": { "type": "plain_text", "text": "Open incident" },
        "url": "https://haaland.local/incidents/INC-2026-0042" }
    ]}
  ]
}
```

The `confirm` dialog is not decoration — it is a documented second intent capture for a production change.

**2. Live thread updates** — every state transition posts into the incident thread, so Slack scrollback and the audit chain tell the same story.

**Dedicated channel per P1:** `conversations.create` → `#inc-2026-0042`, invite service owners from the registry plus the on-call, post the summary, archive on close. This is the "automatically gathers all relevant stakeholders" capability.

### PagerDuty

Events API v2, one endpoint, no SDK:

```python
await http.post("https://events.pagerduty.com/v2/enqueue", json={
    "routing_key": service.pagerduty_integration_key,
    "event_action": "trigger",
    "dedup_key": incident.reference,        # idempotent
    "payload": {
        "summary": f"[{incident.severity}] {incident.title}",
        "severity": {"P1": "critical", "P2": "error"}[incident.severity],
        "source": service.name,
        "custom_details": {"root_cause": ..., "dashboard": ...},
    },
    "links": [{"href": dashboard_url, "text": "Agent Haaland incident"}],
})
```

Use the same `dedup_key` to `resolve` on recovery. Only P1/P2 page.

### Jira

Jira Cloud REST v3, basic auth with `email:api_token`. Only three calls needed:

```
POST /rest/api/3/issue            create
POST /rest/api/3/issue/{k}/comment add evidence
POST /rest/api/3/issue/{k}/attachments  attach post-mortem PDF
```

Description uses Atlassian Document Format, which is verbose JSON — write one `adf.py` helper rather than fighting it inline.

Low-severity path: P3/P4 incidents create a ticket with the full evidence bundle attached and the incident is closed as `triaged_low`. Nobody gets paged.

### Loki (log retrieval)

```python
params = {
    "query": '{service="payments-api"} |= "ERROR" | json | line_format "{{.message}}"',
    "start": int(window.start.timestamp() * 1e9),   # nanoseconds
    "end":   int(window.end.timestamp() * 1e9),
    "limit": 500,
    "direction": "backward",
}
r = await http.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params)
```

**Never send 500 raw log lines to the model.** The `LogSource` implementation must:
1. Fetch up to 500 lines.
2. Group by error signature (normalise numbers, UUIDs, timestamps out of the message).
3. Keep the top 5 signatures by count, with 3 examples each and the total count.
4. Emit that ~40-line summary.

This is a 10× token reduction and it *improves* diagnosis quality — a model reasons better about "this exception occurred 1,847 times starting at 09:11:47" than about 500 near-identical lines.

### Tempo (trace retrieval)

```
GET /api/search?tags=service.name%3Dpayments-api&minDuration=1s&start=..&end=..&limit=20
GET /api/traces/{traceID}
```

Take the slowest trace in the window as the exemplar. Reduce the span tree to: service name, operation, duration, self-time, status, and the top 3 attributes per span. Compute self-time server-side — it is the single most diagnostic number and the model should not have to derive it.

### Prometheus (recovery verification)

```
GET /api/v1/query?query=histogram_quantile(0.99, ...)
GET /api/v1/query_range?query=...&start=..&end=..&step=15s
```

Used in the `verifying` node: poll every 30s for up to 10 minutes, require the SLO metric to stay under threshold for 3 consecutive samples before declaring recovery.

---

## Configuration surface

`.env.example` — every one of these must be documented, and the app must fail fast at startup if a required one is missing.

```bash
# Core
DATABASE_URL=postgresql+asyncpg://haaland:haaland@postgres:5432/haaland
REDIS_URL=redis://redis:6379/0
APP_BASE_URL=https://haaland.example.com
SECRET_KEY=                      # session signing
VAULT_ENCRYPTION_KEY=            # 32-byte base64, AES-GCM for the PII vault

# LLM
ANTHROPIC_API_KEY=
HAALAND_MODEL_PRIMARY=claude-opus-5
HAALAND_MODEL_CHEAP=claude-haiku-4-5
HAALAND_MODEL_REPORT=claude-sonnet-5
HAALAND_LLM_MAX_USD_PER_INCIDENT=2.00

# Observability sources
PROMETHEUS_URL=http://prometheus:9090
LOKI_URL=http://loki:3100
TEMPO_URL=http://tempo:3200
ALERTMANAGER_WEBHOOK_TOKEN=

# GitHub App
GITHUB_APP_ID=
GITHUB_PRIVATE_KEY=              # PEM, base64-encoded
GITHUB_INSTALLATION_ID=
GITHUB_WEBHOOK_SECRET=

# Slack
SLACK_BOT_TOKEN=xoxb-
SLACK_SIGNING_SECRET=
SLACK_DEFAULT_CHANNEL=#incidents

# PagerDuty
PAGERDUTY_ROUTING_KEY=

# Jira
JIRA_BASE_URL=https://acme.atlassian.net
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=OPS

# Behaviour
HAALAND_AUTO_PR_ENABLED=true
HAALAND_APPROVAL_TIMEOUT_MINUTES=30
HAALAND_REQUIRE_TWO_APPROVERS_TIER1=true
HAALAND_DEDUPE_WINDOW_SECONDS=300
HAALAND_VAULT_TTL_HOURS=24
```

---

## Local development: getting webhooks in

GitHub and Slack must reach a public URL.

```bash
cloudflared tunnel --url http://localhost:8000
# or
ngrok http 8000
```

Set the tunnel URL as the GitHub App webhook URL and the Slack Interactivity Request URL. Alertmanager stays on the Docker network and posts to `http://api:8000/webhooks/alertmanager` — no tunnel needed, which is another reason the self-hosted stack is the right prototype choice.

For replaying webhooks without triggering real events, keep captured payloads in `apps/api/tests/fixtures/webhooks/` and a `scripts/replay_webhook.py` that POSTs them with a correctly computed signature. You will use this constantly.
