# 12 — Setup & Integration Guide

How to configure, launch, and verify the Agent Haaland API, what every
consuming application must do before calling it, and what every **target
repository** ("affected repo") needs in place before the agent can debug it.

Everything below is verified against the code in `apps/api/src/haaland/`, not
against the roadmap docs. Where a doc describes something that is **not built
yet**, it is called out explicitly in [§7](#7-what-is-not-implemented-yet).

---

## 1. What is actually implemented today

| Capability | Status |
|---|---|
| `POST /api/debug-sessions` — logs + repo URL in, incident out | ✅ implemented |
| LangGraph debug loop: ingest → redact → classify → clone → locate → diagnose → evaluate → patch → static check → generate tests → run tests → push branch → open PR → **suspend for human approval** | ✅ implemented |
| Approve / reject over HTTP, resuming the checkpointed graph | ✅ implemented |
| Hash-chained audit timeline + chain verification endpoint | ✅ implemented |
| Post-mortem retrieval (JSON or markdown) | ✅ implemented |
| Lark notification — custom webhook bot (one chat, push-only) | ✅ implemented |
| Lark notification — tenant application (org-wide: any chat, DMs, editable cards) | ✅ implemented |
| LLM providers: `fake` (offline), `deepseek` (default real provider), `anthropic`, `openai` | ✅ implemented |
| `POST /webhooks/alertmanager` | ⚠️ auth is real, ingestion returns **501** |
| `POST /webhooks/github` | ⚠️ signature check is real, ingestion returns **501** |
| `POST /webhooks/monitor` (docs/11 generic monitoring contract) | ❌ not implemented |
| Lark callback URL verification (`POST /webhooks/lark/card` challenge) | ✅ implemented |
| Lark interactive approve/reject callback | ❌ not implemented — the endpoint returns **501** |
| Slack, PagerDuty, Jira, ticketing | ❌ `NullTicketProvider`, no Slack adapter |
| **API authentication on `/api/*`** | ❌ **none** — see [§4.2](#42-there-is-no-authentication-on-api-yet) |

The agent **structurally cannot merge**: `SCMProvider`
([integrations/base.py:46](../apps/api/src/haaland/integrations/base.py#L46))
has no `merge()` method and no code path calls one.

---

## 2. Complete secrets & configuration inventory

All settings are read by
[config.py](../apps/api/src/haaland/config.py) via pydantic-settings with the
prefix **`HAALAND_`**, from process env or a `.env` file in the **process
working directory**.

### 2.1 Always required

| Variable | Why | How to produce it |
|---|---|---|
| `HAALAND_SECRET_KEY` | app secret; prod refuses to start on the dev default | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `HAALAND_VAULT_ENCRYPTION_KEY` | Fernet-style key for the PII token vault (redaction reversal); prod refuses the dev default | `python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"` |
| `HAALAND_DATABASE_URL` | Postgres, `postgresql+asyncpg://…` — holds incidents, the audit chain, **and** LangGraph checkpoints | compose provides one |
| `HAALAND_REDIS_URL` | ARQ job queue, token vault storage, LLM budget counters | compose provides one |

`SECRET_KEY` and `VAULT_ENCRYPTION_KEY` have dev defaults that work locally.
With `HAALAND_ENV=prod`, `Settings._no_dev_secrets_in_prod` raises at import
time if either is still the default or if `HAALAND_CORS_ORIGINS` is `*`.

### 2.2 LLM provider — pick exactly one

`HAALAND_LLM_PROVIDER` ∈ `fake` | `deepseek` | `anthropic` | `openai` (default
`fake`; `deepseek` is the default *real* provider).

| Provider | Key required | Enforcement |
|---|---|---|
| `fake` | **none** | deterministic fixtures, zero network, zero spend — the CI/offline default |
| `deepseek` | `HAALAND_DEEPSEEK_API_KEY` | `build_provider` raises `RuntimeError` at startup if missing |
| `anthropic` | `HAALAND_ANTHROPIC_API_KEY` | same |
| `openai` | `HAALAND_OPENAI_API_KEY` | same |

Model IDs default to `deepseek-v4-flash` (primary and cheap) and
`deepseek-v4-pro` (report). They are provider-specific strings: `config.py`
refuses to start if the selected provider and the `HAALAND_MODEL_*` names
disagree (`deepseek-*` / `claude-*` / `gpt-*`), so switching provider means
switching model names in the same edit.

Cost guardrails: `HAALAND_LLM_MAX_USD_PER_INCIDENT` (default `2.00`) and
`HAALAND_LLM_MAX_USD_PER_DAY` (default `50.00`), enforced by `BudgetGuard`
against Redis counters. Those ceilings were sized for Claude pricing; on
`deepseek-v4-flash` they buy roughly two orders of magnitude more traffic, so
lower them if you want the guard to bite.

**DeepSeek specifics** (`llm/providers/deepseek.py`,
`llm/templates/deepseek/README.md`): it is reached through the *OpenAI*-compatible
surface at `HAALAND_DEEPSEEK_BASE_URL` (default `https://api.deepseek.com`), not
the Anthropic-compatible one at `/anthropic` — that endpoint has no
structured-output path and ignores `cache_control`, and it silently remaps
unknown model names to `deepseek-v4-flash`. DeepSeek has JSON mode but no strict
`json_schema` mode, so the schema is appended as a system block and validated
here, with one repair turn before the stage fails as `invalid_output`.

### 2.3 GitHub credentials — two modes

`HAALAND_GITHUB_AUTH_MODE` ∈ `pat` | `app` (default `pat`).

**Mode `pat`** (single-developer fallback):

| Variable | Notes |
|---|---|
| `HAALAND_GITHUB_TOKEN` | fine-grained or classic PAT. If **unset**, `build_credentials` silently falls back to `AnonymousCredentials` — public repos clone fine, but branch creation, commits, and PR creation will fail at runtime, not at startup |

Required PAT permissions on every target repo: **Contents: Read & write**,
**Pull requests: Read & write**. See the label caveat in [§5.4](#54-known-caveats-for-target-repos).

**Mode `app`** (recommended for anything shared):

| Variable | Notes |
|---|---|
| `HAALAND_GITHUB_APP_ID` | required |
| `HAALAND_GITHUB_APP_PRIVATE_KEY` **or** `HAALAND_GITHUB_APP_PRIVATE_KEY_PATH` | PEM inline (newlines as `\n`) or a path to the `.pem` |
| `HAALAND_GITHUB_APP_INSTALLATION_ID` | required |

Missing any of the three → `RuntimeError` at startup with an explicit message.
App mode mints short-lived (~1h) installation tokens per clone and caches them
with a 5-minute refresh margin.

`HAALAND_GITHUB_WEBHOOK_SECRET` only matters for `POST /webhooks/github`,
which currently 501s after verifying the signature.

### 2.4 Notifications (optional)

`HAALAND_NOTIFY_CHANNELS` is a comma-separated list; empty disables
notifications entirely. Today the only accepted value is `lark` — **any other
name raises `ValueError` at startup**.

Lark has two transports, selected by `HAALAND_LARK_MODE`. Both report as
channel `lark` and render the same card; full walkthrough in
[13-lark-integration.md](13-lark-integration.md).

| Variable | Required when |
|---|---|
| `HAALAND_LARK_MODE` | `webhook` (default) — one custom bot, one chat, push-only · `app` — an application installed into the Lark tenant |
| `HAALAND_LARK_DOMAIN` | `global` (default, larksuite.com) or `feishu` (feishu.cn) — separate clouds, separate app registries |
| `HAALAND_LARK_WEBHOOK_URL` | `MODE=webhook` and `lark` is in `NOTIFY_CHANNELS` (else `RuntimeError` at startup) |
| `HAALAND_LARK_WEBHOOK_SECRET` | only if the custom bot has "Signature verification" enabled |
| `HAALAND_LARK_APP_ID` / `HAALAND_LARK_APP_SECRET` | `MODE=app` (else `RuntimeError` at startup) |
| `HAALAND_LARK_DEFAULT_RECEIVE_ID` | `MODE=app` — a `chat_id` (`oc_…`), `open_id` (`ou_…`) or work email; the type is inferred from the prefix |
| `HAALAND_LARK_ENCRYPT_KEY` / `HAALAND_LARK_VERIFICATION_TOKEN` | only to register a Request URL at `POST /webhooks/lark/card` |

Webhook-bot setup: target group chat → Settings → Bots → Add Bot → Custom Bot
→ copy the webhook URL.

App setup, in short: create a custom app in the Lark developer console →
enable the **Bot** feature → grant `im:message`, `im:chat:readonly`
(+ `contact:user.id:readonly` to address people) → **release the version and
have a Lark admin approve it** → add the bot to the target chat → read the
`chat_id` from `GET /api/notifications/lark/chats`. The admin-approval step
is the one that is silently fatal: without it the token exchange succeeds and
every send fails.

Verification (each isolates one failure mode):

```bash
curl -s   localhost:8000/api/notifications/lark/verify   # credentials only
curl -s   localhost:8000/api/notifications/lark/chats    # membership + chat_id
curl -sX POST localhost:8000/api/notifications/test      # real delivery
make lark-check                                          # same, no API needed
```

### 2.5 Behaviour & safety

| Variable | Default | Meaning |
|---|---|---|
| `HAALAND_ENV` | `dev` | `dev` \| `test` \| `compose` \| `prod`. `compose` selects the Docker sandbox runner; anything else selects the host subprocess runner |
| `HAALAND_APP_BASE_URL` | `http://localhost:8000` | used to build dashboard/PR links inside notifications and PR bodies |
| `HAALAND_CORS_ORIGINS` | `*` | comma-separated; `*` is rejected in prod |
| `HAALAND_ALLOW_HOST_TEST_EXECUTION` | `false` | opt-in to running the target repo's (and the model's) pytest **on the host**. Left `false` on a non-isolated runner, the test phase reports `unrunnable` — never a silent `pass` |
| `HAALAND_MAX_FIX_ATTEMPTS` | `3` | patch → check retry ceiling before escalation |
| `HAALAND_APPROVAL_TIMEOUT_MINUTES` | `30` | approval gate timeout |
| `HAALAND_DEDUPE_WINDOW_SECONDS` | `300` | incident dedupe window |
| `HAALAND_REDACTION_ENGINE` | `regex` | `presidio` requires the `[presidio]` extra |
| `HAALAND_VAULT_TTL_HOURS` | `24` | PII token-mapping lifetime in Redis |
| `HAALAND_ALERTMANAGER_WEBHOOK_TOKEN` | — | bearer token for the (501) Alertmanager endpoint |

### 2.6 Minimum viable key sets

```
Offline smoke test (no external calls at all):
  HAALAND_LLM_PROVIDER=fake        # and nothing else — dev defaults cover the rest

Real end-to-end run producing a real PR:
  HAALAND_SECRET_KEY, HAALAND_VAULT_ENCRYPTION_KEY
  HAALAND_LLM_PROVIDER=deepseek + HAALAND_DEEPSEEK_API_KEY
  HAALAND_GITHUB_AUTH_MODE=pat + HAALAND_GITHUB_TOKEN   (or the three APP_* vars)

Add notifications:
  HAALAND_NOTIFY_CHANNELS=lark + HAALAND_LARK_WEBHOOK_URL [+ _SECRET]
```

---

## 3. Part A — Standing up the API (operator steps)

### Prerequisites

- Docker + Docker Compose (compose path), or Python 3.12+ with
  [uv](https://docs.astral.sh/uv/) and local Postgres 16 + Redis 7 (local path)
- `git` on `PATH` in whichever process runs the worker — repos are cloned with GitPython
- Postgres extensions `pgcrypto` and `citext` (the compose image installs them
  via `infra/postgres/init.sql`; migration `0001` also declares them)

### Step 1 — Create the environment file

```bash
cp .env.example .env
```

> **Gotcha:** `Settings` loads `.env` **relative to the process working
> directory**. `docker compose` reads the repo-root `.env` (`env_file: .env`).
> If you run uvicorn manually from `apps/api/`, either run it from the repo
> root or copy `.env` into `apps/api/`.

### Step 2 — Generate the two secrets

```bash
python -c "import secrets;print('HAALAND_SECRET_KEY='+secrets.token_urlsafe(48))"
python -c "import secrets,base64;print('HAALAND_VAULT_ENCRYPTION_KEY='+base64.b64encode(secrets.token_bytes(32)).decode())"
```

Paste both into `.env`. Do this even for dev — it takes ten seconds and
removes the single most common prod-promotion failure.

### Step 3 — Choose the LLM provider

Start with `HAALAND_LLM_PROVIDER=fake`. Prove the plumbing works with zero
spend, then switch to `deepseek` and set `HAALAND_DEEPSEEK_API_KEY` (keys:
platform.deepseek.com -> API keys). Keep the `HAALAND_MODEL_*` defaults.

### Step 4 — Wire GitHub

**Fast path (PAT).** Create a fine-grained PAT scoped to the target repos with
*Contents: Read & write* and *Pull requests: Read & write*. Set:

```bash
HAALAND_GITHUB_AUTH_MODE=pat
HAALAND_GITHUB_TOKEN=github_pat_...
```

**Production path (GitHub App).**

1. GitHub → *Settings → Developer settings → GitHub Apps → New GitHub App*.
2. Repository permissions: **Contents: Read & write**, **Pull requests: Read &
   write**. Grant nothing else — the missing merge capability *is* the safety control.
3. Generate a private key (`.pem`), note the **App ID**.
4. Install the App on the target repositories; the installation URL ends in the
   **installation ID**.
5. Set `HAALAND_GITHUB_AUTH_MODE=app` plus the three `APP_*` variables.

### Step 5 — Notifications (optional)

```bash
HAALAND_NOTIFY_CHANNELS=lark
HAALAND_LARK_WEBHOOK_URL=https://open.larksuite.com/open-apis/bot/v2/hook/xxxx
# HAALAND_LARK_WEBHOOK_SECRET=...   # only if signature verification is on
```

### Step 6 — Bring up the stack

**Compose (recommended):**

```bash
make up          # docker compose up -d --build  → postgres, redis, api, worker
make migrate     # docker compose exec api alembic upgrade head
make logs        # tail api + worker
```

Compose overrides `HAALAND_ENV=compose` and rewrites the DB/Redis URLs to the
service names, so `.env` values for those three are ignored inside containers.

**Local (no containers for the app):**

```bash
docker compose up -d postgres redis
uv sync                           # from the repo root; add --extra presidio / --extra pdf as needed
cd apps/api
uv run alembic upgrade head
uv run uvicorn haaland.main:app --reload            # terminal 1
uv run arq haaland.worker.WorkerSettings            # terminal 2  ← REQUIRED
```

`uv sync` from the repo root is the one command that matters: the root
`pyproject.toml` is a uv **workspace** whose only member is `apps/api`, so a
single root `.venv` and a single root `uv.lock` cover the backend and all of
its tooling. There is no separate lockfile under `apps/api` — running
`uv sync` there resolves to the same workspace environment.

The `openai` package is a required dependency, not an extra: the default
provider (deepseek) speaks the OpenAI-compatible wire format through that SDK.

> **The worker is not optional.** `POST /api/debug-sessions` only *enqueues*.
> With no ARQ worker running, every submission returns `202` and then nothing
> happens for ever.

### Step 7 — Migrations and checkpoint tables

`alembic upgrade head` creates the application schema (`0001_core_schema`,
`0002_incident_reference_seq`). The LangGraph checkpoint tables are created
separately and automatically: `build_checkpointer` calls
`AsyncPostgresSaver.setup()` on every API and worker startup.

### Step 8 — Verify

```bash
curl -s localhost:8000/health                      # {"status":"ok"}
open http://localhost:8000/docs                    # OpenAPI UI
curl -s localhost:8000/api/incidents               # []
curl -s localhost:8000/api/notifications/channels  # {"channels":[...],"lark_mode":"…"}
curl -sX POST localhost:8000/api/notifications/test
```

Check the startup log line: `startup complete env=… llm_provider=…`.

### Production hardening checklist

- [ ] `HAALAND_ENV=prod`, both secrets rotated off their dev defaults
- [ ] `HAALAND_CORS_ORIGINS` set to explicit origins (prod rejects `*`)
- [ ] GitHub App mode, not PAT; App installed only on repos it should touch
- [ ] Branch protection on `main` in every target repo requiring a code-owner review
- [ ] **An authenticating proxy in front of `/api/*`** — see §4.2
- [ ] `HAALAND_ALLOW_HOST_TEST_EXECUTION=false` unless the runner is containerised
- [ ] Budgets (`LLM_MAX_USD_PER_INCIDENT` / `_PER_DAY`) sized for real traffic
- [ ] Postgres backed up — it holds the tamper-evident audit chain *and* the graph checkpoints

---

## 4. Part B — Setup for applications that call Agent Haaland

### 4.1 The contract

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/debug-sessions` | **Submit a debug session.** `202` + `{reference, incident_id, status}` |
| `GET` | `/api/incidents` | 50 most recent incidents |
| `GET` | `/api/incidents/{reference}` | one incident: status, severity, root cause |
| `POST` | `/api/incidents/{reference}/approve` | body `{actor, reason?}` — resumes the graph |
| `POST` | `/api/incidents/{reference}/reject` | body `{actor, reason}` — `reason` is **required**, min 3 chars, and is fed back into the re-draft loop |
| `GET` | `/api/incidents/{reference}/audit` | hash-chained event timeline |
| `GET` | `/api/incidents/{reference}/audit/verify` | recompute and verify the chain |
| `GET` | `/api/incidents/{reference}/postmortem?as_markdown=true` | post-mortem (404 until generated) |
| `GET` | `/api/notifications/channels` · `POST /api/notifications/test?target=` | channel wiring check; `target` overrides the destination for one message |
| `GET` | `/api/notifications/lark/verify` · `/api/notifications/lark/chats` | Lark credentials check · chats the bot is in (`app` mode only) |
| `GET` | `/health` · `/docs` | liveness · OpenAPI |

Submission body (`DebugSessionRequest`):

```json
{
  "repo_url": "https://github.com/acme/orders-api.git",
  "service_name": "orders-api",
  "log_text": "…raw multi-line log text…",
  "base_ref": "main"
}
```

`repo_url` accepts `https://github.com/owner/repo[.git]` or
`git@github.com:owner/repo[.git]`. An unparseable value returns `422`.
`base_ref` defaults to `main` and **must be an existing branch** — the clone is
`git clone --branch <base_ref> --depth 50`.

Approve/reject return `422` unless the incident status is exactly
`awaiting_approval`.

### 4.2 There is no authentication on `/api/*` yet

`api/deps.py::current_user` is an explicit placeholder that returns the
`X-Haaland-Actor` header value, or the literal `"api"`. **No route depends on
it.** Anyone who can reach the port can submit sessions and approve
production-bound remediations.

Before any other app is pointed at this API:

1. Bind it to a private network; do not expose `/api/*` publicly.
2. Put an authenticating reverse proxy / API gateway in front (mTLS, OAuth2
   introspection, or a shared bearer token) and terminate auth there.
3. Set `HAALAND_CORS_ORIGINS` to your exact front-end origins — the middleware
   allows all methods and headers, so a wildcard origin is a real exposure.
4. Have callers send `X-Haaland-Actor: <your-app-name>` and a real `actor` in
   approval bodies. It is not verified, but it is what lands in the audit chain.

### 4.3 Integration steps for a consuming app

1. **Confirm the target repo is onboarded** (Part C) — this is the step teams forget.
2. **Get the base URL and network path** to the API from whoever runs it.
3. **Submit** a session and store the returned `reference` (`INC-YYYY-NNNN`)
   against your own record. This is your correlation key for everything after.
4. **Poll** `GET /api/incidents/{reference}` — the run is asynchronous and takes
   20–90 s plus LLM time. There is no callback, no webhook out, and no SSE
   stream on this path today.
5. **Branch on status**:

   | Status | Meaning for the caller |
   |---|---|
   | `detected` → `enriching` → `triaging` → `diagnosing` | in progress |
   | `triaged_low` | severity band listed in `HAALAND_TICKET_ONLY_SEVERITIES` — a ticket was filed, no fix attempted, terminal. Unreachable with the default (empty) setting, where every band P1-P4 goes to a PR |
   | `awaiting_approval` | a PR exists; call approve or reject |
   | `escalated` | low confidence or the retry ceiling was hit; a human must take over |
   | `closed` | report generated, terminal |
   | `failed` | the run errored — check the audit timeline |

6. **Approve or reject** with a real human identity in `actor`.
7. **Fetch the post-mortem** once `closed`.

Severity routing matters: P3/P4 stops at `file_ticket`; only P1/P2 clones the
repo and drafts a fix.

### 4.4 Reference client

```bash
# submit
REF=$(curl -sS -X POST localhost:8000/api/debug-sessions \
  -H 'content-type: application/json' \
  -H 'X-Haaland-Actor: billing-portal' \
  -d '{"repo_url":"https://github.com/acme/orders-api.git",
       "service_name":"orders-api",
       "base_ref":"main",
       "log_text":"ERROR ZeroDivisionError: division by zero\n  File \"app/pricing.py\", line 8"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['reference'])")

# poll
watch -n5 "curl -s localhost:8000/api/incidents/$REF | python -m json.tool"

# approve
curl -sS -X POST "localhost:8000/api/incidents/$REF/approve" \
  -H 'content-type: application/json' \
  -d '{"actor":"priya@acme.com","reason":"Diff reviewed, matches the traceback"}'
```

```python
import httpx, asyncio

TERMINAL = {"triaged_low", "escalated", "closed", "failed"}

async def debug(repo_url: str, service: str, logs: str, base_url: str) -> dict:
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as c:
        r = await c.post("/api/debug-sessions", json={
            "repo_url": repo_url, "service_name": service,
            "log_text": logs, "base_ref": "main",
        })
        r.raise_for_status()                      # 422 => unparseable repo_url
        ref = r.json()["reference"]

        while True:
            inc = (await c.get(f"/api/incidents/{ref}")).json()
            if inc["status"] in TERMINAL or inc["status"] == "awaiting_approval":
                return inc
            await asyncio.sleep(5)
```

### 4.5 What the caller is responsible for

- **Log text is untrusted and unredacted on arrival.** Redaction happens inside
  the pipeline before anything reaches a model — but the raw text is persisted
  as evidence first. Do not push secrets or credentials through `log_text`.
- **Volume.** There is no server-side log compaction on this path yet
  (docs/11 §2 is a proposal). Send the relevant excerpt — the traceback and
  surrounding lines — not a 2,000-line dump.
- **Cost.** Every P1/P2 submission spends real LLM budget, capped per incident
  and per day. When the daily cap trips, runs fail rather than degrade.
- **Idempotency.** `POST /api/debug-sessions` has **no dedupe** — the dedupe
  primitive described in docs/11 is on the unimplemented webhook path. Two
  identical submissions create two incidents and two PRs. De-duplicate on your side.

---

## 5. Part C — Setup for target ("affected") repositories

These are the repos Agent Haaland clones, patches, and opens PRs against.

### 5.1 Access

- **GitHub App mode:** install the App on the repo. Without an installation,
  clone/branch/commit/PR all fail.
- **PAT mode:** the PAT must cover the repo with *Contents: RW* + *Pull
  requests: RW*.
- Private repos with no credentials configured fall back to anonymous access and
  fail at clone time.

### 5.2 Repository shape

| Requirement | Why |
|---|---|
| The `base_ref` branch exists | cloned with `--branch <base_ref> --depth 50` |
| Python codebase | static checks are `python -m py_compile` and `ruff check`; test generation targets pytest |
| `ruff` config in `pyproject.toml` (recommended) | otherwise ruff defaults apply and may flag pre-existing style as a "failed check", burning retry attempts |
| pytest layout (optional) | tests run only when the sandbox is isolated **or** `HAALAND_ALLOW_HOST_TEST_EXECUTION=true`; otherwise reported `unrunnable`, which still lets the PR proceed |
| `.github/CODEOWNERS`, `CODEOWNERS`, or `docs/CODEOWNERS` (recommended) | reviewers are resolved deterministically from CODEOWNERS, last-matching-pattern-wins. Absent → no reviewers requested |
| Branch protection on `base_ref` (strongly recommended) | the second half of the "cannot self-merge" guarantee |

### 5.3 What the agent will do to the repo

- Creates a branch named **`haaland/{INC-YYYY-NNNN}-{strategy}`** — one glob
  finds and deletes everything it ever created.
- Commits only the changed files (no deletes — `FileChangeAction` has no
  `DELETE` member), then opens a PR into `base_ref`.
- Labels the PR `incident`, `automated`, `needs-review`.
- Requests CODEOWNERS-derived reviewers (failures are suppressed, so a reviewer
  who cannot be assigned never blocks PR creation).
- Never merges. Never pushes to `base_ref`.

### 5.4 Known caveats for target repos

- **Labels need issues write.** `open_pull_request` calls
  `issues.add_labels`, and unlike the reviewer call it is **not** wrapped in a
  suppress — a permission failure there fails the node after the PR already
  exists. If you see this, grant *Issues: Read & write* to the App as well.
- **Compose-mode sandbox.** `DockerRunner` shells out to `docker run -v
  {workspace}:/workspace python:3.12-slim` over the mounted host socket. Two
  things to verify in your environment before trusting compose-mode check
  results: the workspace path is a container path but the bind mount resolves on
  the *host*, and `python:3.12-slim` ships neither `ruff` nor `pytest`. For
  runs that must reach a PR, `HAALAND_ENV=dev` (SubprocessRunner, with ruff on
  the venv `PATH`) is the reliable path today.

### 5.5 Onboarding checklist per repo

- [ ] App installed / PAT scoped, with Contents RW + Pull requests RW
- [ ] `base_ref` branch exists and is protected
- [ ] CODEOWNERS present and its logins are real collaborators
- [ ] `ruff` configured and currently clean on `base_ref`
- [ ] Team told that PRs labelled `automated` are agent-authored and need real review
- [ ] Repo URL recorded in whatever calls the API

---

## 6. Part D — Testing the API

### 6.1 Layer 1 — Unit tests, lint, architecture contracts

```bash
make test    # docker compose exec api pytest -q
make lint    # ruff check + mypy (services, domain) + lint-imports
```

Or locally:

```bash
cd apps/api
uv run pytest -q
uv run ruff check src/
uv run mypy src/haaland/services src/haaland/domain
uv run lint-imports        # services stay framework-free; domain imports nothing of ours
```

On Windows without GNU `make`, run the target's body directly — e.g.
`docker compose exec api pytest -q`. Every target in the `Makefile` is a
one-line wrapper around a `docker compose` invocation.

The suite is offline by design (`tests/unit/`, `tests/redaction/`) and covers
routing, the hash chain, workspace path containment, the redaction no-leakage
boundary, GitHub auth mode selection, patch application, code search, and the
Lark notifier. Note that most application wiring —
`build_deps`, the graph nodes, the HTTP routes — has **no covering tests**, so
layers 2–4 below are not optional.

### 6.2 Layer 2 — Offline smoke test (no keys, no spend)

```bash
HAALAND_LLM_PROVIDER=fake
```

```bash
curl -s localhost:8000/health
curl -sX POST localhost:8000/api/debug-sessions \
  -H 'content-type: application/json' \
  -d '{"repo_url":"https://github.com/octocat/Hello-World.git",
       "service_name":"smoke","base_ref":"master","log_text":"ERROR boom"}'
```

Then confirm the pipeline moved:

```bash
curl -s localhost:8000/api/incidents/INC-2026-0001
curl -s localhost:8000/api/incidents/INC-2026-0001/audit
```

You should see `evidence.collected`, `pii.redacted`, and `ai.classified`
events. The fake provider always classifies **P2**, so the run routes to
`prepare_workspace` and will need real GitHub access to go further — a clone
failure here is expected and is itself a useful check that the audit trail
records failures honestly.

### 6.3 Layer 3 — Contract tests per endpoint

| Check | Expected |
|---|---|
| `POST /api/debug-sessions` with `repo_url: "not a url"` | `422`, `"cannot parse GitHub repo URL"` |
| `GET /api/incidents/INC-9999-0001` | `404` |
| `POST /api/incidents/{ref}/approve` while status is `diagnosing` | `422 incident is diagnosing, not awaiting_approval` |
| `POST /api/incidents/{ref}/reject` with `{"actor":"x"}` (no reason) | `422` — reason is mandatory |
| `POST /webhooks/alertmanager` with no `Authorization` | `401` |
| `POST /webhooks/alertmanager` with a valid bearer | `501` (by design) |
| `POST /webhooks/github` with a bad `X-Hub-Signature-256` | `401` |
| `GET /api/incidents/{ref}/audit/verify` after a full run | chain verified, unbroken |
| `GET /api/incidents/{ref}/postmortem` before generation | `404 postmortem not yet generated` |

### 6.4 Layer 4 — Full end-to-end against a scratch repo

1. Fork or copy `demo/seed_repo/` into a **throwaway** GitHub repo you own.
   It contains a deliberate `ZeroDivisionError` in `app/pricing.py`.
2. Configure a real provider (`anthropic` + key) and real GitHub credentials.
3. Edit `demo/seed_repo/sample_request.json`, replacing
   `https://github.com/<you>/<repo>.git` with your scratch repo.
4. Submit:

   ```bash
   make debug-sample
   ```

5. Watch it: `make logs`, plus polling
   `GET /api/incidents/{reference}` and `/audit`.
6. Expect on GitHub: a branch `haaland/INC-…-code_fix`, a PR labelled
   `incident`/`automated`/`needs-review`, a PR body carrying the automated-content
   banner and the AI root cause, and reviewers from CODEOWNERS.
7. Incident status should reach `awaiting_approval`.
8. Approve:

   ```bash
   curl -sX POST "localhost:8000/api/incidents/$REF/approve" \
     -H 'content-type: application/json' \
     -d '{"actor":"you@example.com","reason":"verified"}'
   ```

9. Expect `closed`, then fetch the post-mortem and verify the audit chain.
10. **Confirm the safety property yourself:** the PR is still open and unmerged.
    Nothing in the codebase can merge it.

### 6.5 Layer 5 — Durability and failure injection

| Test | How | Expected |
|---|---|---|
| Worker restart mid-approval | at `awaiting_approval`: `docker compose kill worker && docker compose up -d worker`, then approve | resumes at the suspended node — checkpoints are in Postgres, keyed `thread_id = incident_id` |
| No worker running | stop the worker, submit a session | `202` returned, status stays `detected` — proves the queue boundary |
| Bad LLM key | set a garbage `HAALAND_DEEPSEEK_API_KEY` | auth error in worker logs, incident does not silently succeed |
| Missing LLM key | `LLM_PROVIDER=deepseek`, key empty | **startup** `RuntimeError` — fail-fast, not a runtime surprise |
| Provider/model mismatch | `LLM_PROVIDER=anthropic` with `MODEL_PRIMARY=deepseek-v4-flash` | **startup** `ValueError` from `config.py` |
| Bad GitHub token | garbage PAT | clone/PR failure surfaced in logs and the audit trail |
| Unknown notify channel | `HAALAND_NOTIFY_CHANNELS=slack` | **startup** `ValueError: unknown notify channel: 'slack'` |
| Lark misconfigured | `NOTIFY_CHANNELS=lark`, no URL | **startup** `RuntimeError` |
| Notification channel down | point the Lark URL at a dead host | `POST /api/notifications/test` reports the failure; a real incident still completes — a dead channel never blocks the pipeline |
| Prod guard | `HAALAND_ENV=prod` with dev defaults | refuses to start, listing every offending value |
| Budget cap | set `LLM_MAX_USD_PER_INCIDENT=0.001` | run stops on the budget guard |
| Path traversal | unit-covered in `tests/unit/test_workspace_containment.py` | writes outside the workspace rejected |
| PII leakage | `tests/redaction/test_no_leakage.py` | no raw PII crosses the model boundary |

### 6.6 Troubleshooting

| Symptom | Cause |
|---|---|
| `202` then nothing forever | ARQ worker not running |
| Startup: `refusing to start in prod: …` | dev secrets or `CORS_ORIGINS=*` with `ENV=prod` |
| Startup: `HAALAND_DEEPSEEK_API_KEY is required…` | provider set to `deepseek` without a key |
| Stage fails with `AIRefusalError`, `stop_reason=invalid_output` | DeepSeek returned json that missed the schema twice; check the stage prompt against `llm/templates/deepseek/README.md` |
| Startup: `github_auth_mode=app requires…` | one of the three `APP_*` values missing |
| `engine not initialised` | `init_engine` never ran — you imported a module outside the app/worker lifespan |
| Clone fails on a private repo | anonymous fallback: `GITHUB_TOKEN` empty in `pat` mode |
| Clone fails: branch not found | `base_ref` does not exist on the target repo |
| Tests always `unrunnable` | non-isolated runner and `ALLOW_HOST_TEST_EXECUTION=false` — expected, not a bug |
| Static checks always fail in compose mode | see the `DockerRunner` caveat, §5.4 |
| Env vars ignored | `.env` is not in the process working directory |
| `postmortem not yet generated` | incident has not reached `closed` |

---

## 7. What is not implemented yet

Do not build a consumer against these — they exist only in the roadmap docs:

- **`POST /webhooks/monitor`** and the `MonitorSignal` contract (docs/11 §1).
  The only ingestion path today is `POST /api/debug-sessions`.
- **Log compaction** (docs/11 §2) — no signature grouping, no token cap on input.
- **Lark interactive approve/reject callbacks** (docs/11 §4, docs/13 §6) —
  `POST /webhooks/lark/card` verifies signatures and answers Lark's URL
  challenge, but a card button tap returns `501`: it needs a
  `users.lark_open_id` mapping and role authorisation first. Approvals
  happen over HTTP.
- **Alertmanager and GitHub webhook ingestion** — verified then `501`.
- **Session auth / seeded user table** — `current_user` is a placeholder.
- **Slack, PagerDuty, Jira, ticketing** — `NullTicketProvider` only.
- **Metric-based recovery verification, deploy correlation, the dashboard
  frontend** — described in docs/01, 04, 06; not in this slice.
- **`make chaos-pool` / `make reset`** referenced by docs/10 — not in the Makefile.
