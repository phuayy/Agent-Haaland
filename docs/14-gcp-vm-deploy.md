# 14 — Deploying and demoing on a Google Cloud VM

Status: implemented · sibling of [12-render-deploy.md](12-render-deploy.md) ·
trigger contract from [11-monitoring-trigger-integration.md](11-monitoring-trigger-integration.md)

A single Compute Engine VM running the full compose stack, terminated by
Caddy with a real TLS certificate, ending in an HTTPS URL you can paste into
an existing Prometheus/Alertmanager deployment as a webhook receiver.

## Why a VM rather than Render

[12-render-deploy.md](12-render-deploy.md) documents two constraints the
managed platform imposes, and both disappear on a VM:

- **The Docker socket exists.** `DockerRunner` can execute the model's
  generated tests in a throwaway sibling container, so a PR can honestly
  claim its tests ran. On Render the sandbox falls back to
  `SubprocessRunner` and the PR says "tests not executed".
- **The disk persists.** Workspace clones survive a restart instead of being
  rebuilt on resume.

The cost is that you own the box: patching, the firewall, and the fact that
mounting `/var/run/docker.sock` into the API container gives that container
root-equivalent control of the VM. That trade is fine for a single-tenant
demo box and is not fine on shared infrastructure.

---

## 1. Machine specs

Every model call is an outbound HTTPS request to DeepSeek or Anthropic, so
**no GPU is involved at any point**. What the VM actually spends cycles on is
`git clone`, `ruff`/`mypy`/`pytest` over the target repository, Postgres, and
the Docker image build. That profile is CPU- and RAM-bound, not
accelerator-bound.

| | Recommended | Minimum |
|---|---|---|
| Machine type | `e2-standard-4` (4 vCPU, 16 GB) | `e2-standard-2` (2 vCPU, 8 GB) |
| Boot disk | 50 GB `pd-balanced` | 30 GB `pd-balanced` |
| Image | Ubuntu 24.04 LTS (x86/64) | same |
| GPU | none | none |

Sizing notes:

- The image build runs `uv sync` over the full dependency tree twice
  (dependencies, then the project). On 2 vCPU that is roughly 6–10 minutes
  and peaks near 8 GB, which is why `bootstrap.sh` adds a 4 GB swapfile —
  without it the OOM killer takes uv down mid-sync on the smaller shape.
- Disk fills from three directions: Docker images (~2.5 GB), Postgres data,
  and per-incident workspace clones. 50 GB leaves headroom for a demo repo
  of any realistic size.
- `e2-standard-4` runs roughly **USD 100–130/month** on-demand depending on
  region — verify against the current [pricing
  calculator](https://cloud.google.com/products/calculator), the number
  moves. **Stop the instance between demos**; a stopped VM bills only for the
  disk and the reserved IP.

---

## 2. Create the VM and reserve an IP

Run these from your workstation with `gcloud` authenticated. Substitute your
own project id; `asia-southeast1` (Singapore) is a reasonable default if you
are in South-East Asia.

```bash
export PROJECT_ID=your-project-id
export REGION=asia-southeast1
export ZONE=asia-southeast1-b

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com

# A static IP, reserved first. The webhook URL you hand to Alertmanager must
# not change every time the VM is stopped and started, and an ephemeral IP does.
gcloud compute addresses create haaland-ip --region "$REGION"
export HAALAND_IP=$(gcloud compute addresses describe haaland-ip \
  --region "$REGION" --format='value(address)')
echo "Static IP: $HAALAND_IP"

gcloud compute instances create haaland-demo \
  --zone "$ZONE" \
  --machine-type e2-standard-4 \
  --image-family ubuntu-2404-lts-amd64 \
  --image-project ubuntu-os-cloud \
  --boot-disk-size 50GB \
  --boot-disk-type pd-balanced \
  --address "$HAALAND_IP" \
  --tags haaland-web \
  --metadata enable-oslogin=TRUE
```

### Firewall

Only 80 and 443 need to face the internet. Port 80 is required — Let's
Encrypt validates over HTTP before Caddy can serve HTTPS.

```bash
gcloud compute firewall-rules create haaland-allow-web \
  --allow tcp:80,tcp:443 \
  --target-tags haaland-web \
  --source-ranges 0.0.0.0/0 \
  --description "Caddy: ACME HTTP-01 challenge + public HTTPS"
```

If your Prometheus/Alertmanager egresses from a known fixed IP, narrow
`--source-ranges` to it for 443. Leave 80 open either way, or certificate
renewal fails 60 days from now, silently.

Postgres (5432) and Redis (6379) are deliberately **not** in that rule, and
`infra/gcp/docker-compose.prod.yml` publishes no host port for either. The
root `docker-compose.yml` binds both to `0.0.0.0` with the password
`haaland`; running that file on a VM with a public IP would put an
internet-reachable database on a known credential. That is the single most
important reason to use the `infra/gcp/` file and pass it with an explicit
`-f`.

### SSH

Prefer IAP over opening port 22 to the world:

```bash
gcloud compute ssh haaland-demo --zone "$ZONE" --tunnel-through-iap
```

---

## 3. Pick the public hostname

Caddy needs a name to request a certificate for.

- **You own a domain:** create an `A` record pointing at `$HAALAND_IP` and
  wait for it to resolve. Use that name.
- **You do not:** use `sslip.io`, which resolves any embedded IP back to
  itself and works with Let's Encrypt. For `34.126.100.20` the hostname is
  `34-126-100-20.sslip.io`.

```bash
# On your workstation:
echo "${HAALAND_IP//./-}.sslip.io"
```

Confirm DNS before starting Caddy — ACME failures are rate-limited:

```bash
dig +short "${HAALAND_IP//./-}.sslip.io"   # must print $HAALAND_IP
```

---

## 4. Bootstrap the VM

```bash
gcloud compute ssh haaland-demo --zone "$ZONE" --tunnel-through-iap

# On the VM:
git clone https://github.com/<you>/agent-haaland.git ~/haaland
cd ~/haaland
bash infra/gcp/bootstrap.sh
exit          # log out and back in so the docker group applies
```

`bootstrap.sh` installs Docker Engine and the compose plugin from Docker's
own apt repository, adds you to the `docker` group, creates the swapfile, and
caps container log rotation (the default `json-file` driver never rotates and
will eventually fill the disk with worker logs).

---

## 5. Configure secrets

Two separate files, and confusing them is the most common setup error:

| File | Read by | Contents |
|---|---|---|
| `.env` (repo root) | the application, via `env_file` | every `HAALAND_*` setting |
| `infra/gcp/.env.compose` | docker compose itself, via `--env-file` | hostname, Postgres credentials, PEM path, and `HAALAND_API_AUTH_TOKEN` |

`HAALAND_API_AUTH_TOKEN` is the one value that has to appear in both, with
the same content. The `web` container reads it from `.env.compose` instead
of `env_file: ../../.env` so that an internet-facing container is not also
handed the GitHub token, the LLM keys, and the vault key. A mismatch is
silent at startup and shows up as every dashboard panel reporting
"invalid or missing API token".

```bash
cd ~/haaland
cp .env.example .env
cp infra/gcp/.env.compose.example infra/gcp/.env.compose
```

Generate the values `config.py` refuses to start in prod without
(`_no_dev_secrets_in_prod`):

```bash
python3 - <<'PY'
import base64, secrets
print("HAALAND_SECRET_KEY=" + secrets.token_urlsafe(32))
print("HAALAND_VAULT_ENCRYPTION_KEY=" + base64.b64encode(secrets.token_bytes(32)).decode())
print("HAALAND_API_AUTH_TOKEN=" + secrets.token_urlsafe(32))
print("HAALAND_ALERTMANAGER_WEBHOOK_TOKEN=" + secrets.token_urlsafe(32))
print("POSTGRES_PASSWORD=" + secrets.token_urlsafe(24))
PY
```

Edit `.env` so that, with `DOMAIN` standing for the hostname from step 3:

```bash
HAALAND_ENV=prod
HAALAND_APP_BASE_URL=https://DOMAIN
# .env.example ships this as http://localhost:3000 and it takes precedence
# over APP_BASE_URL (config.py dashboard_url). Left at the copied value,
# every notification button links to a page only reachable from the VM.
HAALAND_DASHBOARD_BASE_URL=https://DOMAIN
HAALAND_CORS_ORIGINS=https://DOMAIN          # must not be "*" in prod
HAALAND_SECRET_KEY=<generated>
HAALAND_VAULT_ENCRYPTION_KEY=<generated>
HAALAND_API_AUTH_TOKEN=<generated>               # guards every /api/* route
HAALAND_ALERTMANAGER_WEBHOOK_TOKEN=<generated>   # guards /webhooks/alertmanager

HAALAND_LLM_PROVIDER=deepseek
HAALAND_DEEPSEEK_API_KEY=sk-...

HAALAND_GITHUB_AUTH_MODE=app
HAALAND_GITHUB_APP_ID=...
HAALAND_GITHUB_APP_INSTALLATION_ID=...
HAALAND_GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github-app.pem

HAALAND_NOTIFY_CHANNELS=lark
HAALAND_LARK_MODE=webhook
HAALAND_LARK_WEBHOOK_URL=https://open.larksuite.com/open-apis/bot/v2/hook/...
```

`HAALAND_ALERTMANAGER_WEBHOOK_TOKEN` and `HAALAND_API_AUTH_TOKEN` are
separate on purpose. The first only lets a caller open an incident; the
second lets a caller read every incident and **approve remediations**. A
monitoring platform should never hold the second.

Then edit `infra/gcp/.env.compose`:

```bash
HAALAND_DOMAIN=DOMAIN
POSTGRES_USER=haaland
POSTGRES_PASSWORD=<generated>
POSTGRES_DB=haaland
GITHUB_APP_PEM_PATH=/home/YOUR_USER/haaland/secrets/github-app.pem
```

Copy the GitHub App private key up, from your workstation:

```bash
gcloud compute scp ./secrets/github-app.pem haaland-demo:~/haaland/secrets/ \
  --zone "$ZONE" --tunnel-through-iap
# then, on the VM:
chmod 600 ~/haaland/secrets/github-app.pem
```

Leave `GITHUB_APP_PEM_PATH` empty when `HAALAND_GITHUB_AUTH_MODE=pat`.

---

## 6. Start the stack

The `--env-file` and `-f` flags are required on **every** compose command
here. Naming a file with `-f` also stops compose auto-loading
`docker-compose.override.yml`, which mounts host source and runs
`uvicorn --reload` — both wrong on a public box.

Define a shell alias so you cannot forget:

```bash
cd ~/haaland
echo "alias hc='docker compose --env-file infra/gcp/.env.compose -f infra/gcp/docker-compose.prod.yml'" \
  >> ~/.bashrc
source ~/.bashrc

hc up -d --build          # first build: 5-10 minutes
hc exec api alembic upgrade head
hc exec api python scripts/seed_services.py   # demo services for the dashboard
hc ps
```

The seed step is optional but the dashboard is a blank registry without it:
the deployed build is read-only (Caddy fronts a `web` container that forwards
GET only), so "Add Service" is disabled there and the first services have to
arrive server-side — from this script, or from the first debug session, which
registers its service automatically.

Verify, from the VM and then from outside it:

```bash
hc exec api curl -sS localhost:8000/health          # {"status":"ok"}
curl -sS https://DOMAIN/health                       # same, over TLS
curl -sSI https://DOMAIN/incidents | head -1         # HTTP/2 200 from web:3000
```

The third command is the one that catches a Caddy or `web` misconfiguration:
a `{"detail":"Not Found"}` body there means the request reached the API
instead of the dashboard, and every notification button will be dead.

If the second command fails, `hc logs caddy` will say why. Almost always it
is DNS not yet resolving to the VM, or port 80 blocked so the ACME challenge
could not complete.

Check the API came up in prod mode rather than crash-looping on a missing
secret:

```bash
hc logs api | grep "startup complete"
# startup complete env=prod llm_provider=deepseek
```

---

## 7. The trigger URL

This is the link you give your Prometheus deployment:

```
POST https://DOMAIN/webhooks/alertmanager
Authorization: Bearer <HAALAND_ALERTMANAGER_WEBHOOK_TOKEN>
Content-Type: application/json
```

It accepts the standard **Alertmanager v4 webhook payload** — no adapter, no
translation layer. The handler
(`apps/api/src/haaland/api/webhooks/alertmanager.py`) verifies the bearer
token, extracts the target repository, flattens the alert group into the
evidence text the pipeline consumes, claims a dedupe key, enqueues the
LangGraph run, and returns `202` in well under 500 ms. Nothing is analysed in
the request path.

### What the alert must carry

Alertmanager offers no request-body templating, so the repository has to
travel as alert metadata. The handler resolves each key from the most
specific scope outwards — the individual alert's `annotations`, then its
`labels`, then `commonAnnotations`, `commonLabels`, `groupLabels`:

| Key | Required | Meaning |
|---|---|---|
| `repo_url` | **yes** | Repository to clone, diff, and open the PR against |
| `repo_ref` | no | Base branch (default `main`) |
| `service` / `service_name` / `job` / `alertname` | no | Incident's service name; first present wins |

An alert with no `repo_url` is rejected with **422** and an explanatory
message rather than dropped. There is no workspace to clone without one, and
a silent drop means the rule author discovers months later that their alerts
went nowhere — the 422 surfaces in Alertmanager's own notification log
immediately.

### Response codes

| Code | Body | Meaning |
|---|---|---|
| `202` | `{"reference": "INC-...", "incident_id": "...", "status": "detected"}` | Incident opened, job enqueued |
| `202` | `{"status": "deduplicated", ...}` | Same `groupKey` already seen inside `HAALAND_DEDUPE_WINDOW_SECONDS` |
| `202` | `{"status": "ignored", ...}` | `resolved` notification, or no firing alerts in the group |
| `401` | — | Bad or missing bearer token |
| `422` | — | No `repo_url`, or a `repo_url` that is not a parseable GitHub URL |

### Wire it up

`infra/gcp/prometheus-example/` holds a working pair of configs to copy from.
On your Prometheus host:

```yaml
# alertmanager.yml
route:
  receiver: haaland
  group_by: [alertname, service]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: haaland
    webhook_configs:
      - url: https://DOMAIN/webhooks/alertmanager
        send_resolved: false
        max_alerts: 20
        http_config:
          authorization:
            type: Bearer
            credentials: <HAALAND_ALERTMANAGER_WEBHOOK_TOKEN>
```

```yaml
# rules/haaland.yml — the repo_url annotation is the whole integration
groups:
  - name: haaland-demo
    rules:
      - alert: HighErrorRate
        expr: sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
              / sum(rate(http_requests_total[5m])) by (service) > 0.05
        for: 2m
        labels: { severity: critical, service: payments-api }
        annotations:
          summary: "5xx rate above 5% on {{ $labels.service }}"
          description: "Error ratio {{ $value | humanizePercentage }} over 5m."
          repo_url: "https://github.com/acme/payments-api"
```

Reload both:

```bash
curl -X POST http://your-prometheus:9090/-/reload
curl -X POST http://your-alertmanager:9093/-/reload
```

Keep `repeat_interval` longer than `HAALAND_DEDUPE_WINDOW_SECONDS` (default
300s). A repeat inside the window returns `deduplicated`; one outside it
opens a second incident, which is correct for an alert still firing hours
later.

### Test it without waiting for a real alert

Post an Alertmanager-shaped payload by hand. Use a fresh `groupKey` each
time, or the dedupe window returns `deduplicated` and nothing runs.

```bash
curl -i -X POST https://DOMAIN/webhooks/alertmanager \
  -H "Authorization: Bearer $HAALAND_ALERTMANAGER_WEBHOOK_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{
    \"version\": \"4\",
    \"groupKey\": \"test-$(date +%s)\",
    \"status\": \"firing\",
    \"receiver\": \"haaland\",
    \"commonLabels\": {\"alertname\": \"HighErrorRate\", \"service\": \"payments-api\"},
    \"commonAnnotations\": {\"repo_url\": \"https://github.com/<you>/<demo-repo>\"},
    \"alerts\": [{
      \"status\": \"firing\",
      \"labels\": {\"alertname\": \"HighErrorRate\", \"severity\": \"critical\"},
      \"annotations\": {\"summary\": \"5xx rate above 5%\", \"description\": \"TimeoutError: connection pool exhausted after 5000ms\"},
      \"startsAt\": \"2026-08-21T09:12:03Z\",
      \"fingerprint\": \"test01\"
    }]
  }"
```

Then watch it work:

```bash
hc logs -f worker
curl -sS https://DOMAIN/api/incidents -H "Authorization: Bearer $HAALAND_API_AUTH_TOKEN" | jq
```

Or force a real alert end to end from Prometheus itself by pushing a rule
whose `expr` is `vector(1)` — it fires within `group_wait` and exercises the
whole path including Alertmanager's own grouping and auth.

---

## 8. Running the demo

The narrative in [10-demo-script.md](10-demo-script.md) applies unchanged.
Surfaces on this deployment:

| Surface | URL |
|---|---|
| Liveness | `https://DOMAIN/health` |
| Interactive OpenAPI | `https://DOMAIN/docs` |
| Incident list | `GET https://DOMAIN/api/incidents` |
| Incident detail | `GET https://DOMAIN/api/incidents/{reference}` |
| Audit chain verification | `GET https://DOMAIN/api/incidents/{reference}/audit/verify` |
| Approve / reject | `POST https://DOMAIN/api/incidents/{reference}/approve` |
| Post-mortem | `GET https://DOMAIN/api/incidents/{reference}/postmortem` |
| Dashboard (read-only) | `https://DOMAIN/incidents` and `https://DOMAIN/incidents/{reference}` |

All of those need `Authorization: Bearer $HAALAND_API_AUTH_TOKEN`. `/docs`
renders without it, but its "Try it out" calls will 401 until you paste the
token into the **Authorize** dialog.

The direct-input path still works and is the better opener for a live demo
because it needs no alert to fire:

```bash
curl -sS -X POST https://DOMAIN/api/debug-sessions \
  -H "Authorization: Bearer $HAALAND_API_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"repo_url":"https://github.com/<you>/<demo-repo>","service_name":"payments-api","base_ref":"main","log_text":"TimeoutError: connection pool exhausted after 5000ms"}'
```

Both entrypoints funnel through `api/ingest.py`, so what a Prometheus alert
triggers and what this command triggers are the same run.

### The Next.js dashboard

`apps/web` runs in this stack as the `web` service and Caddy serves it at the
same domain: `/api/*`, `/webhooks/*`, `/health`, and the OpenAPI pages go to
`api:8000`, everything else to `web:3000`. That is what makes
`https://DOMAIN/incidents/{reference}` — the link on every Lark card — resolve
to a page rather than to the API's `{"detail":"Not Found"}`.

**It is read-only, and it is not access-controlled.** The dashboard cannot
send an `Authorization` header without shipping the token in its JavaScript
bundle, where any visitor could read it and then approve remediations at will.
Instead the browser calls a same-origin Next route handler at `/dash-api/*`
(`apps/web/src/app/dash-api/[...path]/route.ts`) which attaches the token
server-side and forwards **GET only**; approve, reject, and debug-session
creation return `405` there and stay first-party API calls made with your own
token. The approval panel and the Trigger button render disabled and say so.

Reads are still exposed: anyone who reaches the domain can see incident logs,
root causes, diffs, and repo names. Put IAP, a VPN, or a source-range firewall
rule in front of it before treating the URL as anything but demo-visible.

---

## 9. Operating it

```bash
hc ps                      # what is running
hc logs -f api worker      # follow both
hc exec api pytest -q      # the suite, inside the container
hc restart api worker      # after editing .env
hc down                    # stop, keep volumes
hc down -v                 # stop and DESTROY the database
```

`.env` is read at container start, so any change needs `hc restart api worker`
— the API will not pick it up otherwise.

Deploying a new commit:

```bash
cd ~/haaland && git pull
hc up -d --build
hc exec api alembic upgrade head
```

Stop billing between demos, keeping the disk, the IP, and all data:

```bash
gcloud compute instances stop haaland-demo --zone "$ZONE"
gcloud compute instances start haaland-demo --zone "$ZONE"
# restart: unless-stopped brings the stack back on its own
```

### Backing up before a demo

```bash
hc exec -T postgres pg_dump -U haaland haaland | gzip > ~/haaland-$(date +%F).sql.gz
```

---

## 10. Cost

| Item | Approximate monthly |
|---|---|
| `e2-standard-4`, running continuously | USD 100–130 |
| 50 GB `pd-balanced` | ~USD 6 |
| Reserved static IP, while the VM runs | free |
| Reserved static IP, while the VM is stopped | ~USD 3 |
| Egress | negligible at demo volume |
| DeepSeek tokens | capped by `HAALAND_LLM_MAX_USD_PER_DAY` (default $50) |

Compute Engine prices vary by region and change; verify against the current
[pricing calculator](https://cloud.google.com/products/calculator). Stopping
the instance between demos reduces the bill to disk plus IP, roughly USD
9/month.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `refusing to start in prod: ...` in `hc logs api` | One of the prod-required secrets is unset or still the dev default | The message names each one; fix `.env`, then `hc restart api worker` |
| Caddy loops on ACME | DNS not pointing at the VM, or port 80 closed | `dig +short DOMAIN`; confirm the firewall rule covers `tcp:80` |
| Webhook returns 401 | Token mismatch | `hc exec api printenv HAALAND_ALERTMANAGER_WEBHOOK_TOKEN` and compare byte for byte with Alertmanager's |
| Webhook returns 422 `repo_url` | The alerting rule has no `repo_url` annotation | Add it to the rule and reload Prometheus |
| Webhook 202s but nothing happens | Worker down, or the response said `deduplicated` | `hc ps`; read the response body; retry with a fresh `groupKey` |
| Lark card's Incident button shows `{"detail":"Not Found"}` | The request reached `api:8000`, so either `web` is not running or the Caddy fallback block is missing | `hc ps web`; `curl -sSI https://DOMAIN/incidents`; confirm `infra/gcp/Caddyfile` ends with a bare `handle` pointing at `web:3000` |
| Every dashboard panel shows "invalid or missing API token" | `HAALAND_API_AUTH_TOKEN` differs between `infra/gcp/.env.compose` and `.env` | Compare `hc exec web printenv HAALAND_API_AUTH_TOKEN` with `hc exec api printenv HAALAND_API_AUTH_TOKEN`, then `hc up -d web` |
| Approve in the dashboard returns 405 | Working as designed — the dashboard forwards GET only | Approve from Lark, or `POST /api/incidents/{ref}/approve` with your own bearer token |
| Build OOM-killed | 2 vCPU shape without swap | `bootstrap.sh` adds a 4 GB swapfile — rerun it |
| PR says "tests not executed" | Docker socket not mounted | Confirm `/var/run/docker.sock` appears in `hc config`; do **not** set `HAALAND_ALLOW_HOST_TEST_EXECUTION=true`, which would run model-written code inside the API container |
| Disk full | Old images and dangling build cache | `docker system prune -af` (add `--volumes` only after checking `hc ps -a`) |
