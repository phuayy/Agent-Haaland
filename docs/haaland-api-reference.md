# Haaland API Reference

Frontend integration guide for the FastAPI backend in `apps/api`.
Generated from source: `src/haaland/api/` (routes, webhooks, schemas), `src/haaland/domain/models.py`, `src/haaland/db/models/`.

**Base URL** — `HAALAND_APP_BASE_URL`, default `http://localhost:8000`
**App title / version** — `Agent Haaland` `0.1.0`
**Interactive docs** — `GET /docs`, `GET /redoc`, `GET /openapi.json` (FastAPI defaults, not disabled)

---

## Read this before you write a single hook

Three things about this backend will change how you build the data layer.

### 1. Every `/api/*` endpoint needs one bearer token — and it identifies no one

Send it on every request:

```
Authorization: Bearer <HAALAND_API_AUTH_TOKEN>
```

`require_api_auth` in [security.py:19](apps/api/src/haaland/api/security.py#L19) is attached to all eight `/api` routers in [router.py:20-31](apps/api/src/haaland/api/router.py#L20-L31). Missing or wrong gives `401` with `{"detail": "invalid or missing API token"}` and a `WWW-Authenticate: Bearer` header. `/webhooks/*` is exempt on purpose — each webhook verifies its own upstream signature instead. `/health`, `/docs`, `/redoc`, and `/openapi.json` are open.

An unset token means open access. That is a development convenience only: `config.py` refuses to start with `HAALAND_ENV=prod` unless a token is set, so it can never silently no-op on a public deployment.

The token is a shared secret, not an identity. There is one for the whole deployment — no per-client tokens, no scopes — and it authorizes approving AI-authored code changes, so treat it accordingly and never put it in a browser bundle.

**On `X-Haaland-Actor`:** don't send it. `current_user()` in [deps.py:27](apps/api/src/haaland/api/deps.py#L27) reads the header (falling back to the literal string `"api"`), but no route declares it as a dependency — it is unreferenced. The actor for an approval or rejection is carried in the **JSON body** (`actor` field), which is deliberate; see the comment on `ApprovalRequest`. Nothing verifies that value.

If you want to be forward-compatible, sending `X-Haaland-Actor` is harmless — it's just inert. But don't build your hooks assuming it identifies anyone.

### 2. Every write is asynchronous — you must poll

`POST /api/debug-sessions`, `/approve`, and `/reject` all enqueue an arq job to Redis and return immediately. The HTTP response tells you the work was *accepted*, never that it *happened*. The real state machine runs in a separate worker process (`worker.py`).

The polling target is `GET /api/incidents/{reference}` and its `status` field. There are no websockets, no SSE, and no long-poll endpoint.

### 3. Three endpoints are deliberately stubs

`POST /webhooks/alertmanager`, `POST /webhooks/github`, and the card-action branch of `POST /webhooks/lark/card` authenticate the caller for real and then return **`501 Not Implemented`**. They are not broken and not worth wiring up in the UI.

---

## CORS

Configured in [main.py:47](apps/api/src/haaland/main.py#L47) from `HAALAND_CORS_ORIGINS` (comma-separated; default `*`, which the config layer refuses to allow in prod). `allow_methods` and `allow_headers` are both `*`. Note that `allow_credentials` is **not** set, so it defaults to `False` — `fetch(..., { credentials: 'include' })` will fail CORS until that changes.

---

## Error shapes

Two distinct shapes, and your error handling needs to tell them apart.

**Raised `HTTPException` — `detail` is a string:**

```json
{ "detail": "incident INC-2026-0001 not found" }
```

**Pydantic request validation failure (always `422`) — `detail` is an array:**

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "repo_url"],
      "msg": "Field required",
      "input": { "service_name": "checkout" }
    }
  ]
}
```

Note the collision: `POST /api/debug-sessions` and the approve/reject endpoints can return `422` from *either* source. Branch on `Array.isArray(body.detail)`.

---

## Shared vocabulary

### `IncidentStatus`
`detected` · `enriching` · `triaging` · `triaged_low` · `diagnosing` · `awaiting_approval` · `escalated` · `approved` · `rejected` · `remediating` · `verifying` · `documenting` · `closed` · `failed`

Only `awaiting_approval` accepts approve/reject. Terminal-ish states for UI purposes: `closed`, `failed`, `escalated`, `triaged_low`.

### `Severity`
`P1` · `P2` · `P3` · `P4` — nullable until classification runs.

### `ActorType` (audit events)
`system` · `ai` · `human` · `integration`

### Incident `reference`
Format `INC-{year}-{nnnn}`, e.g. `INC-2026-0001`. Postgres-sequence-backed, zero-padded to 4 digits but not capped at 4. **This is the URL key for every incident endpoint — not the UUID.**

### Timestamps
All timestamp columns are Postgres `timestamptz`, serialized by FastAPI's default JSON encoder to ISO 8601 **with offset**: `"2026-08-20T14:22:31.847293+00:00"`. Safe for `new Date(...)`.

---

# Endpoints

## Health

### `GET /health`

Liveness probe. Defined inline on the app, outside the API router — no prefix, and outside the bearer-token dependency.

| | |
|---|---|
| **Auth** | None |
| **Request** | No body, no params |

**`200 OK`**
```json
{ "status": "ok" }
```

It returns `ok` unconditionally once the process is up. It does not check Postgres, Redis, or the LLM provider — so it is a liveness signal, not a readiness one.

---

## Debug Sessions

> `src/haaland/api/routes/debug_sessions.py` · tag `debug-sessions`

### `POST /api/debug-sessions`

**The primary entrypoint.** Submits logs plus a repo URL, opens an incident, writes the first audit event, and enqueues the `run_debug_session` job. This is the only endpoint that creates work.

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Content-Type** | `application/json` |
| **Success status** | `202 Accepted` (explicitly set, not 200) |

**Request body** — `DebugSessionCreate`, which subclasses the domain `DebugSessionRequest`:

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `repo_url` | `string` | ✅ | — | GitHub only. Accepts `https://github.com/owner/repo`, `git@github.com:owner/repo`, `owner/repo`, with or without `.git`. Parsed by `parse_repo_url`. |
| `service_name` | `string` | ✅ | — | Free text. Becomes the incident title as `Debug session — {service_name}`. |
| `log_text` | `string` | ✅ | — | Raw log/traceback text. No length limit declared at this layer. |
| `base_ref` | `string` | ❌ | `"main"` | Branch the fix is based on. |

No extra-field restriction is configured, so unknown keys are silently ignored rather than rejected.

**Example request**
```json
{
  "repo_url": "https://github.com/acme/checkout-api",
  "service_name": "checkout-api",
  "log_text": "Traceback (most recent call last):\n  File \"app/pricing.py\", line 42...",
  "base_ref": "main"
}
```

**`202 Accepted`** — `DebugSessionAccepted`

| Field | Type | Notes |
|---|---|---|
| `reference` | `string` | `INC-2026-0001`. **Store this** — it keys every follow-up call. |
| `incident_id` | `string` | UUID, stringified. Not accepted by any route as a lookup key; informational. |
| `status` | `string` | Always the literal `"detected"`. Hardcoded, not read back from the DB. |

```json
{
  "reference": "INC-2026-0001",
  "incident_id": "3f2b9c14-8d1e-4a77-9f3a-1c0b5e6d7a82",
  "status": "detected"
}
```

**Errors**

| Status | When | `detail` |
|---|---|---|
| `422` | `repo_url` unparseable | String: `cannot parse GitHub repo URL: '...'` |
| `422` | Missing/mistyped field | Array (Pydantic) |

**Hook notes**
- The incident row is committed **before** the job is enqueued, so the reference is immediately valid for `GET /api/incidents/{reference}` even if the worker is down or backed up.
- `status: "detected"` is a constant. Don't treat it as live state — start polling.

---

## Incidents

> `src/haaland/api/routes/incidents.py` · tag `incidents`

### `GET /api/incidents`

Most recent incidents, newest first.

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Params** | **None.** No pagination, no filtering, no search. |

Hard-coded `ORDER BY detected_at DESC LIMIT 50`. There is no offset parameter and no total count — if you need pagination or a status filter, it needs a backend change.

**`200 OK`** — array of objects (no `response_model`; shape is the literal dict built in the handler):

| Field | Type | Notes |
|---|---|---|
| `reference` | `string` | |
| `title` | `string` | |
| `status` | `string` | `IncidentStatus` |
| `severity` | `string \| null` | `P1`–`P4`; null before triage |
| `detected_at` | `string` | ISO 8601 + offset |
| `closed_at` | `string \| null` | |

```json
[
  {
    "reference": "INC-2026-0002",
    "title": "Debug session — checkout-api",
    "status": "awaiting_approval",
    "severity": "P2",
    "detected_at": "2026-08-20T14:22:31.847293+00:00",
    "closed_at": null
  }
]
```

Returns `[]` when empty. Never 404s.

---

### `GET /api/incidents/{reference}`

Full detail for one incident. **This is your polling endpoint.**

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Path param** | `reference` — `string`, e.g. `INC-2026-0001` |

**`200 OK`** — the list shape plus four fields:

| Field | Type | Notes |
|---|---|---|
| `reference` | `string` | |
| `title` | `string` | |
| `service_name` | `string \| null` | Registry name of the service the incident was opened against, read from the `services` row via `primary_service_id`. `null` only if that row was deleted. Do **not** parse it out of `title` — that string's format belongs to the service layer. |
| `status` | `string` | `IncidentStatus` |
| `severity` | `string \| null` | |
| `severity_confidence` | `number \| null` | Float `0.0`–`1.0`, from the classifier |
| `repo_full_name` | `string \| null` | `owner/repo` |
| `base_ref` | `string \| null` | Branch the fix is drafted against, e.g. `main`. Combine with `repo_full_name` and an evidence `source_ref` to build a GitHub blob link. |
| `root_cause_summary` | `string \| null` | Populated after diagnosis |
| `detected_at` | `string` | |
| `closed_at` | `string \| null` | |

Note: `closed_reason`, `id`, and the intermediate lifecycle timestamps (`triaged_at`, `approved_at`, `recovered_at`, …) exist on the DB model but are **not** exposed here.

**Errors**

| Status | `detail` |
|---|---|
| `404` | `incident INC-2026-0001 not found` |

---

### `POST /api/incidents/{reference}/approve`

Approves a pending remediation and enqueues `resume_debug_session`. Valid only while the incident is in `awaiting_approval`.

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` — the actor is a separate **body field**, self-asserted and unverified |
| **Content-Type** | `application/json` |
| **Path param** | `reference` — `string` |

**Request body** — `ApprovalRequest`:

| Field | Type | Required | Constraints |
|---|---|---|---|
| `actor` | `string` | ✅ | `min_length=1`, `max_length=200` |
| `reason` | `string \| null` | ❌ | `max_length=2000`; defaults to `null` |

```json
{ "actor": "tyler@acme.com", "reason": "Reviewed the diff, ships it" }
```

**`200 OK`**
```json
{ "status": "resuming" }
```

That is the entire response. It confirms the job was queued — not that the incident advanced.

**Errors**

| Status | When | `detail` |
|---|---|---|
| `404` | Unknown reference | `incident INC-2026-0001 not found` |
| `422` | Wrong state | `incident is diagnosing, not awaiting_approval` (string) |
| `422` | Bad body | Array (Pydantic) |

---

### `POST /api/incidents/{reference}/reject`

Same mechanics as approve, one contractual difference: **`reason` is required.** The rejection reason is fed back into the model's re-draft loop, so a reasonless rejection isn't actionable.

**Request body** — `RejectionRequest`:

| Field | Type | Required | Constraints |
|---|---|---|---|
| `actor` | `string` | ✅ | `min_length=1`, `max_length=200` |
| `reason` | `string` | ✅ | `min_length=3`, `max_length=2000` |

```json
{ "actor": "tyler@acme.com", "reason": "Patch drops the null check on line 88" }
```

**`200 OK`** — `{ "status": "resuming" }`. Errors identical to approve.

**Hook note:** enforce `reason.length >= 3` client-side. It's the one field where the two endpoints diverge, and it's an easy source of a confusing 422.

---

## Services

> `src/haaland/api/routes/services.py` · tag `services`

The registry of monitored microservices, backed by the `services` table from migration 0001. The dashboard's service cards read this — health, incident counts, and the last-incident line are **derived per request** from incidents whose `primary_service_id` points at the service, so there is nothing to keep in sync client-side.

Any debug session also *creates* a service row when its `service_name` is not registered yet (`api/ingest.py`), which means a session submitted by curl or by the Alertmanager webhook still shows up here.

### `GET /api/services`

Every registered service, ordered by name.

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Params** | **None.** No pagination or filtering — filter client-side. |

**`200 OK`** — array of:

| Field | Type | Notes |
|---|---|---|
| `id` | `string` | UUID |
| `name` | `string` | Unique. This is the `service_name` to send to `POST /api/debug-sessions` |
| `repo_full_name` | `string \| null` | `owner/repo` |
| `repo_url` | `string \| null` | Canonical `https://github.com/owner/repo`, safe to link |
| `base_ref` | `string` | Default branch to patch; `main` when unset |
| `tier` | `number` | `1` core, `2` standard, `3` internal |
| `owner_team` | `string \| null` | |
| `runbook_url` | `string \| null` | |
| `created_at` | `string` | ISO 8601 + offset |
| `health` | `string` | `healthy` \| `p1` \| `p2` — derived, never stored |
| `incident_count` | `number` | All incidents ever linked (capped at the 500 most recent across the whole registry) |
| `active_incident_count` | `number` | Not `closed`, `triaged_low`, or `rejected` |
| `last_incident` | `object \| null` | `reference`, `title`, `status`, `severity`, `detected_at`, `closed_at` |

`health` is a pure function of the service's incidents (`domain/health.py`): an open `P1` gives `p1`; any other open incident — including one not yet classified, which is most of a run's life — gives `p2`; everything resolved gives `healthy`. `failed` and `escalated` incidents count as open.

```json
[
  {
    "id": "432c8c68-5dc1-48e9-a69b-e9504c22b0f1",
    "name": "orders-api",
    "repo_full_name": "haaland-demo/orders-api",
    "repo_url": "https://github.com/haaland-demo/orders-api",
    "base_ref": "main",
    "tier": 1,
    "owner_team": "Team Orders",
    "runbook_url": null,
    "created_at": "2026-08-21T12:14:03.138179Z",
    "health": "p1",
    "incident_count": 3,
    "active_incident_count": 1,
    "last_incident": {
      "reference": "INC-2026-0007",
      "title": "Debug session — orders-api",
      "status": "remediating",
      "severity": "P1",
      "detected_at": "2026-08-21T12:14:55.592823Z",
      "closed_at": null
    }
  }
]
```

Returns `[]` on a freshly migrated database. `python scripts/seed_services.py` (or `make seed`) puts four demo services in it.

---

### `POST /api/services`

Register a service.

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Body** | `application/json` |

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | `string` | yes | 1–200 chars, unique |
| `repo_url` | `string \| null` | no | Any GitHub URL form (`https://`, `git@`, `.git` suffix); stored canonicalised |
| `base_ref` | `string` | no | Default `main` |
| `tier` | `number` | no | `1`–`3`, default `2` |
| `owner_team` | `string \| null` | no | |
| `runbook_url` | `string \| null` | no | |

**`201 Created`** — the same object `GET /api/services` returns, with zero counts.

**Errors**

| Status | `detail` |
|---|---|
| `409` | `a service named 'orders-api' is already registered` |
| `422` | `cannot parse GitHub repo URL: 'not-a-url'` |

---

### `GET /api/services/{service_id}`

One service, same shape as the list entry. Its counts come from the 50 most recent incidents on that service.

**Errors** — `404` `service {id} not found` (also for a malformed UUID).

---

### `GET /api/services/{service_id}/incidents`

Incident history for one service, newest first, capped at 50.

**`200 OK`** — array of `reference`, `title`, `status`, `severity`, `detected_at`, `closed_at` — the same shape as `last_incident` above.

**Errors** — `404` `service {id} not found`.

---

## Audit Trail

> `src/haaland/api/routes/audit.py` · tag `audit` · same `/api/incidents` prefix

### `GET /api/incidents/{reference}/audit`

The incident timeline — the hash-chained, append-only event log. Ordered by `seq` ascending (oldest first, the inverse of the incident list).

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Path param** | `reference` — `string` |

**`200 OK`** — array:

| Field | Type | Notes |
|---|---|---|
| `seq` | `integer` | 1-based, gapless, unique per incident |
| `event_type` | `string` | Dotted, e.g. `debug_session.submitted` |
| `actor_type` | `string` | `system` · `ai` · `human` · `integration` |
| `actor_label` | `string` | Display name, e.g. `api` |
| `summary` | `string` | Human-readable line — render this |
| `occurred_at` | `string` | ISO 8601 + offset |

```json
[
  {
    "seq": 1,
    "event_type": "debug_session.submitted",
    "actor_type": "human",
    "actor_label": "api",
    "summary": "Debug session submitted for checkout-api (acme/checkout-api@main)",
    "occurred_at": "2026-08-20T14:22:31.847293+00:00"
  }
]
```

The underlying rows also carry `payload` (JSONB), `actor_id`, `prev_hash`, and `hash` — **none are exposed.** No pagination; the full chain is returned every call.

**Errors:** `404` — `incident INC-2026-0001 not found`

**Hook note:** this endpoint is the natural driver for a live timeline view. Since it's append-only and `seq`-ordered, you can diff on `seq` and append rather than re-rendering.

---

### `GET /api/incidents/{reference}/audit/verify`

Recomputes every hash in the chain and reports whether it is intact. This is the compliance self-check.

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Path param** | `reference` — `string` |

**`200 OK`**

| Field | Type | Notes |
|---|---|---|
| `valid` | `boolean` | |
| `events_checked` | `integer` | On success, total events. On failure, the `seq` where verification stopped. |
| `first_divergence_seq` | `integer \| null` | `null` when valid |

```json
{ "valid": true, "events_checked": 14, "first_divergence_seq": null }
```

Tampered:
```json
{ "valid": false, "events_checked": 7, "first_divergence_seq": 7 }
```

**Errors:** `404` — `incident INC-2026-0001 not found`

Cost is O(events) with a SHA-256 per event — cheap, but don't put it on a poll loop. Fetch on demand.

---

## Postmortems

> `src/haaland/api/routes/postmortems.py` · tag `postmortems` · same `/api/incidents` prefix

### `GET /api/incidents/{reference}/postmortem`

Returns the generated postmortem. **This endpoint is content-negotiated by query param and returns two different content types.**

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Path param** | `reference` — `string` |
| **Query param** | `as_markdown` — `boolean`, default `false` |

**`200 OK` with `as_markdown=false` (default)** — `application/json`:

| Field | Type | Notes |
|---|---|---|
| `version` | `integer` | Starts at 1; regeneration bumps it |
| `markdown` | `string` | Full document |
| `generated_at` | `string` | ISO 8601 + offset |

```json
{
  "version": 1,
  "markdown": "# Postmortem: INC-2026-0001\n\n## Summary\n...",
  "generated_at": "2026-08-20T14:31:02.113847+00:00"
}
```

**`200 OK` with `as_markdown=true`** — `text/markdown`, raw body, **no JSON envelope**:

```
# Postmortem: INC-2026-0001

## Summary
...
```

Calling `.json()` on that response throws. Use `.text()`.

**Errors** — two distinct 404s worth distinguishing in the UI:

| Status | `detail` | Meaning |
|---|---|---|
| `404` | `incident INC-2026-0001 not found` | Bad reference |
| `404` | `postmortem not yet generated` | Valid incident, no postmortem yet — an expected state, not an error |

**Hook note:** the second 404 fires for any incident that hasn't reached `documenting`/`closed`. Treat it as "empty", not "failed", or your postmortem tab will flash an error for the entire life of every active incident.

---

## Evidence

> `src/haaland/api/routes/evidence.py` · tag `evidence` · same `/api/incidents` prefix

### `GET /api/incidents/{reference}/evidence`

Read-only mirror of the `evidence` table — what the agent actually collected before diagnosing. Ordered oldest-first.

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Path param** | `reference` — `string` |

**`200 OK`** — array:

| Field | Type | Notes |
|---|---|---|
| `kind` | `string` | `log` · `trace` · `metric` · `deploy` · `config` · `runbook` · `source` |
| `source` | `string` | e.g. `user_upload`, `workspace` |
| `source_ref` | `string \| null` | For `kind: "source"`, a `path:start_line-end_line` reference into the target repo. For `kind: "trace"`, the raise site as `path:line` |
| `content` | `object` | Shape varies by `kind` — see below |
| `relevance` | `number \| null` | `0.0`–`1.0` |
| `collected_at` | `string` | ISO 8601 + offset |

**What's actually in `content` today** — checked against the node implementations that write these rows, since the shape isn't obvious from the column type (`JSONB`, no schema):

- `kind: "log"` — `{"line_count": 47}`. **The raw log text is not here and is not retrievable from any endpoint.** It lives only in the transient LangGraph checkpoint state, never persisted to a queryable table. This row is a count, not a viewer.
- `kind: "source"` — `{"reason": "traceback_frame", "confidence": 0.9}`. `reason` is one of `traceback_frame` / `function_name_grep` / `error_signature_grep` / `symbol_reference (...)`. Combine with `source_ref` and the incident's `repo_full_name` + `base_ref` (from `GET /api/incidents/{reference}`) to build a GitHub link: `https://github.com/{repo_full_name}/blob/{base_ref}/{path}#L{start}-L{end}`.

- `kind: "trace"` — the failure path, written once by the `locate_code` node when the ingested log yielded a traceback or an error signature. **The row is absent entirely otherwise** (alert-shaped incidents), and its absence is the signal that no observed path exists — not an empty `frames` array.

```json
{
  "call_chain": ["quote", "apply_discount", "average_item_price"],
  "frames": [
    { "depth": 0, "path": "/app/app/main.py", "line": 11, "function": "quote" },
    { "depth": 1, "path": "/app/app/pricing.py", "line": 12, "function": "apply_discount" },
    { "depth": 2, "path": "/app/app/pricing.py", "line": 8, "function": "average_item_price" }
  ],
  "exception_class": "ZeroDivisionError",
  "exception_message": "division by zero"
}
```

  - `depth` is the frame's index in the traceback, which is the order the request travelled: `0` is the outermost entry point, the highest depth is the raise site.
  - `call_chain` is the same path as bare function names with `<module>` frames dropped; `frames` keeps them, so the two lists are not index-aligned.
  - `frames[].path` is the path **as the runtime saw it** — a container absolute like `/app/app/pricing.py`, not a repository path. It is not linkable on its own: match it against a `kind: "source"` row's `source_ref` by trailing path segments, and link only what resolves.
  - `exception_message` is redacted before it is stored (it is rendered runtime data and can carry PII); `exception_class` and the frame paths are not.

```json
[
  { "kind": "log", "source": "user_upload", "source_ref": null, "content": { "line_count": 47 }, "relevance": 1.0, "collected_at": "2026-08-20T14:22:35+00:00" },
  { "kind": "source", "source": "workspace", "source_ref": "app/pricing.py:40-55", "content": { "reason": "traceback_frame", "confidence": 0.9 }, "relevance": 0.9, "collected_at": "2026-08-20T14:22:41+00:00" }
]
```

Returns `[]` before evidence collection has run. Never 404s except for an unknown `reference`.

**Errors:** `404` — `incident INC-2026-0001 not found`

---

## Remediation

> `src/haaland/api/routes/remediation.py` · tag `remediation` · same `/api/incidents` prefix

### `GET /api/incidents/{reference}/remediation`

The drafted fix(es) — read this before approving. Read-only mirror of the `remediations` table, oldest attempt first (there can be more than one: `HAALAND_MAX_FIX_ATTEMPTS` allows retries after a rejected or failed attempt).

| | |
|---|---|
| **Auth** | `Authorization: Bearer <token>` |
| **Path param** | `reference` — `string` |

**`200 OK`** — array:

| Field | Type | Notes |
|---|---|---|
| `strategy` | `string` | `revert_deploy` · `config_restore` · `scale_resource` · `disable_feature_flag` · `failover` · `code_fix` · `manual_investigation` |
| `rationale` | `string` | Why this strategy |
| `risk_notes` | `string \| null` | |
| `repo_full_name` | `string` | |
| `branch_name` | `string` | The branch the PR is drafted on |
| `base_sha` | `string` | |
| `patch` | `string` | **Full unified diff** — genuinely populated before the incident reaches `awaiting_approval`. Real content, not a placeholder. |
| `attempt_count` | `integer` | |
| `pr_number` | `integer \| null` | Null until the PR is actually opened |
| `pr_url` | `string \| null` | |
| `status` | `string` | `pending` · `approved` · `rejected` · `merged` · `superseded` · `expired` |
| `created_at` | `string` | ISO 8601 + offset |
| `resolved_at` | `string \| null` | |

```json
[
  {
    "strategy": "code_fix",
    "rationale": "The discount calculation divides by a stale denominator...",
    "risk_notes": "Touches the pricing hot path; covered by existing unit tests.",
    "repo_full_name": "acme/checkout-api",
    "branch_name": "haaland/fix-inc-2026-0001",
    "base_sha": "a1b2c3d",
    "patch": "diff --git a/app/pricing.py b/app/pricing.py\n--- a/app/pricing.py\n+++ b/app/pricing.py\n@@ -40,7 +40,7 @@\n...",
    "attempt_count": 1,
    "pr_number": 42,
    "pr_url": "https://github.com/acme/checkout-api/pull/42",
    "status": "pending",
    "created_at": "2026-08-20T14:29:10+00:00",
    "resolved_at": null
  }
]
```

**No `approvals` array on these rows.** The `approvals` DB table is defined but nothing in the codebase ever writes to it — who approved/rejected an attempt, when, and why is recorded correctly in the audit chain (`GET /api/incidents/{reference}/audit`, `event_type: "approval.granted"` / `"approval.denied"`) instead. Read it from there.

Returns `[]` before a remediation has been drafted.

**Errors:** `404` — `incident INC-2026-0001 not found`

**Hook note:** the frontend's approve/reject UI should fetch this alongside the incident before rendering the decision panel — approving without showing `patch` first defeats the point of a human-in-the-loop gate.

---

## Notification Diagnostics

> `src/haaland/api/routes/notifications.py` · tag `notifications`

Operator-facing wiring checks. Read-only, no secrets in any response. Worth surfacing on a settings/admin screen — they're the only endpoints that expose backend configuration.

### `GET /api/notifications/channels`

Which notification channels are live.

**`200 OK`**

| Field | Type | Notes |
|---|---|---|
| `channels` | `string[]` | e.g. `["lark"]`. Empty array when `HAALAND_NOTIFY_CHANNELS` is unset. |
| `lark_mode` | `string` | `"webhook"` \| `"app"` |
| `lark_domain` | `string` | `"global"` (larksuite.com) \| `"feishu"` (feishu.cn) |

```json
{ "channels": ["lark"], "lark_mode": "app", "lark_domain": "global" }
```

Never errors.

---

### `GET /api/notifications/lark/verify`

Forces a fresh `tenant_access_token` exchange. Proves app id, secret, and domain agree with Lark. Proves nothing about scopes or chat membership.

**`200 OK`**

| Field | Type | Notes |
|---|---|---|
| `app_id` | `string` | Not a secret |
| `base_url` | `string` | Resolved Lark API host |
| `token_expires_in_seconds` | `integer` | Typically ~7200 |

**Errors**

| Status | When | `detail` |
|---|---|---|
| `409` | Lark app transport not configured | Long string naming the exact env vars required |
| `502` | Lark rejected or was unreachable | Stringified `LarkAPIError` |

---

### `GET /api/notifications/lark/chats`

Chats the bot is a member of. This is how an operator discovers a `chat_id` for `HAALAND_LARK_DEFAULT_RECEIVE_ID`. Requires the `im:chat:readonly` scope.

**`200 OK`**

| Field | Type |
|---|---|
| `chats` | `Array<{ chat_id: string \| null, name: string \| null, description: string \| null }>` |
| `count` | `integer` |

```json
{
  "chats": [
    { "chat_id": "oc_a1b2c3d4", "name": "SRE — Incidents", "description": "" }
  ],
  "count": 1
}
```

Page size is fixed at 100 server-side; no pagination is exposed.

**Errors:** `409` (not configured) · `502` (Lark error) — same shapes as `/lark/verify`.

**Copy note:** an empty list means the bot hasn't been added to any chat, **not** that credentials are wrong. Say that in the UI — it's the single most common misdiagnosis this endpoint exists to prevent.

---

### `POST /api/notifications/test`

Sends a real test message through every configured channel.

| | |
|---|---|
| **Request body** | **None.** This is a POST with no body. |
| **Query param** | `target` — `string \| null`, optional |

`target` overrides the channel default for this one message: a Lark `chat_id` (`oc_…`), `open_id` (`ou_…`), or work email. Transports bound to a fixed destination — a custom webhook bot — ignore it.

**`200 OK` — normal case:**
```json
{
  "results": [
    { "channel": "lark", "status": "sent", "external_ref": "om_x1y2z3", "detail": null }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `results[].channel` | `string` | |
| `results[].status` | `string` | `"sent"` \| `"failed"` |
| `results[].external_ref` | `string \| null` | Message id when sent; null on failure |
| `results[].detail` | `string \| null` | Error text when failed |

**`200 OK` — no channels configured, different shape entirely:**
```json
{
  "channels": [],
  "detail": "no notify channels configured (HAALAND_NOTIFY_CHANNELS)"
}
```

**Watch this one.** Both responses are `200`, but the second has **no `results` key**. `data.results.map(...)` throws. Check for `results` before iterating.

Also note: a delivery failure is reported as `status: "failed"` inside a `200`, not as an HTTP error. One channel being down must never fail the pipeline, so nothing here throws.

---

## Webhooks

> `src/haaland/api/webhooks/` · tag `webhooks`

Third-party inbound endpoints. **Your frontend should not call these.** Documented so you can recognize them in the OpenAPI schema and skip them.

### `POST /webhooks/alertmanager`

| | |
|---|---|
| **Auth** | `Authorization: Bearer <HAALAND_ALERTMANAGER_WEBHOOK_TOKEN>`, constant-time compared |
| **Declared status** | `202` |
| **Actual behavior** | `401` on bad token, else **`501`** |

`501 detail`: `alert-triggered ingestion is not implemented in this slice; submit via POST /api/debug-sessions instead`

### `POST /webhooks/github`

| | |
|---|---|
| **Auth** | `X-Hub-Signature-256: sha256=<hmac>` over the **raw body**, `HAALAND_GITHUB_WEBHOOK_SECRET` |
| **Declared status** | `202` |
| **Actual behavior** | `401` on bad signature, else **`501`** |

`501 detail`: `GitHub webhook ingestion (deploy correlation) is not implemented in this slice`

### `POST /webhooks/lark/card`

The Lark app's "Request URL". Partially implemented — the URL verification handshake works; card actions do not.

**Headers** (when an Encrypt Key is configured):

| Header | Type | Notes |
|---|---|---|
| `X-Lark-Request-Timestamp` | `string` | 5-minute replay window enforced |
| `X-Lark-Request-Nonce` | `string` | |
| `X-Lark-Signature` | `string` | `sha256(timestamp + nonce + encrypt_key + raw_body)` — a plain digest, which is Lark's actual scheme, not an HMAC |

Order of operations: verify signature against raw bytes → decrypt (`encrypt` envelope field) → parse JSON → check the shared verification token.

**`200 OK`** — the only successful path, `type: "url_verification"`:
```json
{ "challenge": "<echoed challenge>" }
```

**Everything else:**

| Status | When |
|---|---|
| `400` | Body isn't valid JSON, decrypted body isn't valid JSON, or `url_verification` with no `challenge` |
| `401` | Bad signature, decryption failure, or verification token mismatch |
| `501` | Any non-`url_verification` payload — i.e. every real card tap |
| `503` | Neither `HAALAND_LARK_ENCRYPT_KEY` nor `HAALAND_LARK_VERIFICATION_TOKEN` set; or an encrypted callback arrived with no encrypt key configured |

`501 detail`: `lark interactive callbacks are not implemented (docs/11 §4); approve or reject via POST /api/incidents/{reference}/approve`

---

# Building the data layer

### The one flow that matters

```
POST /api/debug-sessions              → 202 { reference }
  ↓ poll GET /api/incidents/{reference}
  ↓ status: detected → enriching → triaging → diagnosing → awaiting_approval
POST /api/incidents/{reference}/approve   → 200 { status: "resuming" }
  ↓ keep polling
  ↓ status: approved → remediating → verifying → documenting → closed
GET /api/incidents/{reference}/postmortem
```

Branches off that spine: `triaged_low` (auto-closed, low severity), `escalated` (handed to a human), `rejected` → back through the re-draft loop, `failed`.

### Suggested hook surface

| Hook | Endpoint | Notes |
|---|---|---|
| `useIncidents()` | `GET /api/incidents` | Capped at 50, no params — poll on an interval |
| `useIncident(ref)` | `GET /api/incidents/{ref}` | Poll while status isn't terminal; stop when `closed`/`failed`/`escalated`/`triaged_low` |
| `useAuditTimeline(ref)` | `GET /api/incidents/{ref}/audit` | Append-only — diff on `seq` |
| `useChainVerification(ref)` | `GET /api/incidents/{ref}/audit/verify` | On demand only |
| `useEvidence(ref)` | `GET /api/incidents/{ref}/evidence` | Candidate-locations list **and** the `trace` row the failure-path graph is built from, not a log viewer — see the Evidence section |
| `useRemediation(ref)` | `GET /api/incidents/{ref}/remediation` | Fetch before rendering the approve/reject panel — it's the diff |
| `usePostmortem(ref)` | `GET /api/incidents/{ref}/postmortem` | Treat `postmortem not yet generated` as empty |
| `useCreateDebugSession()` | `POST /api/debug-sessions` | Returns `reference` — navigate to it |
| `useApprove(ref)` / `useReject(ref)` | `POST .../approve` · `.../reject` | Invalidate the incident + audit queries; resume polling |
| `useNotificationChannels()` | `GET /api/notifications/channels` | Admin screen |
| `useServices()` | `GET /api/services` | The service registry — poll it; `health` and the counts are computed server-side |
| `useServiceIncidents(id)` | `GET /api/services/{id}/incidents` | History for one service, newest first |
| `useCreateService()` | `POST /api/services` | Invalidate `["services"]` on success |

### Traps, collected

1. **`{ status: "resuming" }` is not a state change.** Re-poll; don't optimistically set `approved`.
2. **`/notifications/test` has two 200 shapes.** Guard on `results`.
3. **`?as_markdown=true` returns `text/markdown`.** `.text()`, not `.json()`.
4. **`detail` is a string *or* an array.** Both arrive as 422 on the same endpoints.
5. **`reference`, not `incident_id`, is the URL key.** The UUID is returned but accepted nowhere.
6. **`GET /api/incidents` is capped at 50 with no pagination.** Plan the UI around that, or file a backend ticket.
7. **`X-Haaland-Actor` does nothing.** Actor identity travels in the approve/reject body.
8. **`credentials: 'include'` will fail CORS** — `allow_credentials` defaults to `False`.
