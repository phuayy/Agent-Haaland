# 12 — Deploying to Render (PROD)

The repo ships a [render.yaml](../render.yaml) Blueprint. This document is the runbook around it: what gets created, what you must supply by hand, and which product behaviours differ from the Docker Compose environment described in docs 00–11.

## Topology

| Render resource | Name | What it runs |
| --- | --- | --- |
| Web service (Docker) | `haaland-api` | `uvicorn haaland.main:app` — the FastAPI app, health-checked on `/health` |
| Background worker (Docker) | `haaland-worker` | `arq haaland.worker.WorkerSettings` — the LangGraph incident workflow |
| Postgres | `haaland-db` | Application schema + LangGraph checkpoints |
| Key Value | `haaland-kv` | arq job queue, AES-GCM redaction vault, budget counters |

Both services build the same image from `apps/api/Dockerfile` with the **repo root as build context** (the uv workspace lockfile lives there). Only the command differs.

## First deploy

1. **Create the Blueprint** — New → Blueprint → point at this repo. Render reads `render.yaml` and provisions all four resources.
2. **Fill the prompted secrets** (the `sync: false` keys in the `haaland-shared` env group). Required for the app to boot in prod — `config.py` refuses dev defaults:
   - `HAALAND_SECRET_KEY` — any strong random string.
   - `HAALAND_VAULT_ENCRYPTION_KEY` — 32 bytes base64: `python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"`
   - `HAALAND_API_AUTH_TOKEN` — bearer token every `/api/*` call must send (`Authorization: Bearer …`): `python -c "import secrets;print(secrets.token_urlsafe(32))"`
   - `HAALAND_CORS_ORIGINS` — comma-separated dashboard origins; `*` is refused in prod.
   - `HAALAND_APP_BASE_URL` — the public URL of `haaland-api` (used in PR bodies and notification links).
   - `HAALAND_DEEPSEEK_API_KEY`, GitHub App credentials, Lark settings — per [.env.example](../.env.example). Paste the GitHub App PEM inline with `\n` for newlines (`HAALAND_GITHUB_APP_PRIVATE_KEY`); the `_PATH` variant is for local files and does not apply on Render.
3. **Migrations** run automatically: `haaland-api` has `preDeployCommand: alembic upgrade head`, executed once per deploy before traffic shifts. The worker never migrates. (Pre-deploy commands need a paid instance type; on free instances open a shell on the service and run `alembic upgrade head` by hand after the first deploy and after any migration-bearing release.)
4. **Verify**: `GET /health` → `{"status":"ok"}`; `POST /api/debug-sessions` without the bearer token → 401; with it → 202.

## Connection strings — do not fight them

- Render injects `postgres://…` / `postgresql://…`. `config.py` normalises bare schemes to `postgresql+asyncpg://` (the only runtime driver installed), so the injected value works as-is. Explicit `+driver` URLs pass through untouched.
- Both services use the **internal** database/Key Value URLs (same private network), so no TLS parameters are needed. If you ever point at the external Postgres URL, asyncpg does not accept `sslmode=` — prefer the internal URL instead.
- `maxmemoryPolicy: noeviction` on Key Value is deliberate: evicting keys would drop queued jobs, redaction maps, or budget counters.

## Behavioural differences vs Compose (accepted, by design)

| Area | On Render | Why |
| --- | --- | --- |
| Sandbox | `SubprocessRunner`; generated tests report **unrunnable**, PRs state "tests not executed" — never claimed green | No Docker socket. Do **not** set `HAALAND_ALLOW_HOST_TEST_EXECUTION=true`: that executes model-written code inside your service container. Static checks (py_compile, ruff) still run — they parse, never execute. |
| Workspaces | Clones live on ephemeral disk; rebuilt at the checkpointed `base_sha` on resume (`WorkspaceService.ensure`), deleted at terminal nodes | A restart/redeploy between approval-suspend and resume must not kill the run. |
| Job runtime | `HAALAND_ARQ_JOB_TIMEOUT_SECONDS` (default 1800s) caps one debug session | arq's 300s default cancels real runs mid-flight. |
| Frontend | Not deployed — `apps/web` is a mock-data prototype, not wired to the API | See docs/06 vs current slice. |

## Scaling limits (current architecture)

- **One worker instance.** arq itself coordinates via Redis, but a resumed graph rebuilds workspaces locally and the budget/vault design assumes modest concurrency. Scale the API horizontally if needed; keep the worker at 1 until workspaces move to shared storage.
- Alertmanager/GitHub webhook ingestion return 501 in this slice — the supported entrypoint is `POST /api/debug-sessions`.

## Rotating credentials

All secrets rotate in the Render dashboard (env group `haaland-shared`) followed by a redeploy of both services. The GitHub App installation token is minted per clone and expires hourly on its own; rotating the PEM invalidates future mints only.
