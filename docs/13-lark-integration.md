# 13 — Lark (Feishu) Integration: Connect, Configure, Verify

Status: implemented (outbound) · extends [04-integrations.md](04-integrations.md),
[11-monitoring-trigger-integration.md](11-monitoring-trigger-integration.md) §4,
[12-setup-and-integration-guide.md](12-setup-and-integration-guide.md) §2.4

How to connect Agent Haaland to a Lark organisation, prove the connection
works before an incident depends on it, and what the bot can and cannot do
once connected.

---

## 1. Pick a transport first

Lark offers two bot models. They are not "simple vs advanced versions of the
same thing" — they have different identities and different ceilings, and the
choice decides which environment variables matter.

| | `HAALAND_LARK_MODE=webhook` | `HAALAND_LARK_MODE=app` |
|---|---|---|
| What it is | Custom bot living in **one** group chat | Internal application installed into the **Lark tenant** |
| Onboarding | Anyone who can edit the chat, ~2 minutes | Needs a Lark admin to approve the app release |
| Can post to | That one chat, forever | Any chat the bot is added to, plus direct messages |
| Address a person | ✗ | ✓ by `open_id` or work email |
| Edit a card it posted | ✗ | ✓ (`PATCH /open-apis/im/v1/messages/{id}`) |
| Receive an Approve/Reject tap | ✗ (platform limit) | ✓ once docs/11 §4 lands — see [§6](#6-what-is-not-implemented) |
| Credentials | one webhook URL (+ optional secret) | `app_id` / `app_secret`, `tenant_access_token` refreshed automatically |

Rule of thumb: **`webhook` for a demo or a single ops channel; `app` for an
organisation.** The approval gate is the safety-critical interaction, and
only `app` can ever carry it, so anything heading for production should be
onboarded as an app.

Both transports render the identical card
([integrations/notify/lark/cards.py](../apps/api/src/haaland/integrations/notify/lark/cards.py)),
and both report as channel `lark` upstream — switching modes changes no
code, no audit shape, and nothing in the incident pipeline.

---

## 2. Path A — custom webhook bot (fastest)

1. Open the target Lark group chat → **Settings → Bots → Add Bot → Custom Bot**.
2. Name it (e.g. "Agent Haaland"), copy the **webhook URL**.
3. Optional but recommended: enable **Signature verification**, copy the secret.
4. Configure:

   ```bash
   HAALAND_NOTIFY_CHANNELS=lark
   HAALAND_LARK_MODE=webhook
   HAALAND_LARK_WEBHOOK_URL=https://open.larksuite.com/open-apis/bot/v2/hook/xxxxxxxx
   HAALAND_LARK_WEBHOOK_SECRET=            # only if step 3 was enabled
   ```

5. Verify — see [§4](#4-verification-in-order).

Caveat worth knowing before you build on it: if the bot also has a keyword
allowlist configured, Lark silently rejects messages that do not contain a
keyword, with `code != 0`. The adapter surfaces that as a
`NotificationError` rather than swallowing it.

---

## 3. Path B — Lark organisation app (the real integration)

### 3.1 Create the application

1. Go to the developer console for **your** Lark cloud — they are separate
   registries and an `app_id` from one is meaningless on the other:
   - International (Lark): <https://open.larksuite.com/app> → `HAALAND_LARK_DOMAIN=global`
   - China (飞书/Feishu): <https://open.feishu.cn/app> → `HAALAND_LARK_DOMAIN=feishu`
2. **Create custom app** → give it a name, icon and description. "Custom
   app" (internal, one tenant) is the right type; "Store app" is for public
   distribution and is not what this is.
3. **Credentials & Basic Info** → copy **App ID** (`cli_…`) and **App Secret**.

### 3.2 Add the bot capability

**Features → Bot → Enable**. Without this the app exists but cannot send
anything, and `im/v1/messages` fails with a permission error rather than an
obvious "no bot" error.

### 3.3 Grant the minimum scopes

**Permissions & Scopes** — grant exactly these:

| Scope | Needed for |
|---|---|
| `im:message` or `im:message:send_as_bot` | posting the incident/approval cards |
| `im:chat:readonly` | `GET /api/notifications/lark/chats` (discovering `chat_id`) |
| `contact:user.id:readonly` | mapping a code owner's work email to an `open_id` (optional; only if you route to individuals) |

Deliberately **not** granted: message read scopes, file scopes, calendar,
approval. The bot writes notifications; it has no business reading the
organisation's conversations. Same posture as the GitHub App in
[04-integrations.md](04-integrations.md#github--the-least-privilege-core-of-the-safety-story).

### 3.4 Release the app

**Version Management & Release → Create version → Submit for release.** A
Lark **admin must approve** it. Until they do, the token exchange succeeds
but every `im/v1` call fails — which is the single most common "it doesn't
work and I don't know why" case in Lark onboarding. If [§4](#4-verification-in-order)
step 1 passes and step 2 fails, check this first.

### 3.5 Add the bot to the target chat

Open the group chat → **Settings → Bots → Add Bot** → pick your app.

A bot that is not in the chat cannot post to it, no matter how many scopes
it has: sends fail with `code 230002`-family errors.

### 3.6 Configure Agent Haaland

```bash
HAALAND_NOTIFY_CHANNELS=lark
HAALAND_LARK_MODE=app
HAALAND_LARK_DOMAIN=global              # or feishu
HAALAND_LARK_APP_ID=cli_xxxxxxxxxxxx
HAALAND_LARK_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
HAALAND_LARK_DEFAULT_RECEIVE_ID=oc_xxxxxxxxxxxxxxxx   # from §4 step 2
```

`HAALAND_LARK_DEFAULT_RECEIVE_ID` accepts a `chat_id` (`oc_…`), an
`open_id` (`ou_…`), a `union_id` (`on_…`) or a work email; the id *type* is
inferred from the prefix, so no second setting is needed for the common
cases. `HAALAND_LARK_DEFAULT_RECEIVE_ID_TYPE` (default `chat_id`) is only
consulted for ids with no recognisable prefix.

Misconfiguration fails at **startup**, not at the first incident: `lark` in
`NOTIFY_CHANNELS` with `MODE=app` and no `APP_ID` raises `RuntimeError`
before the API serves a request
([registry.py](../apps/api/src/haaland/integrations/notify/registry.py)).

---

## 4. Verification, in order

Each step isolates one failure mode. Run them in order and stop at the first
failure — a later step failing after an earlier one passed tells you exactly
where the problem is.

### Step 1 — credentials

```bash
curl -s localhost:8000/api/notifications/lark/verify | jq
# {"app_id":"cli_…","base_url":"https://open.larksuite.com","token_expires_in_seconds":7199}
```

Proves `app_id`, `app_secret` and `HAALAND_LARK_DOMAIN` agree with Lark.
Proves nothing about scopes, release approval or chat membership.

### Step 2 — chat membership and `chat_id` discovery

```bash
curl -s localhost:8000/api/notifications/lark/chats | jq
# {"chats":[{"chat_id":"oc_9f3…","name":"SRE — prod alerts","description":""}],"count":1}
```

Copy the `chat_id` into `HAALAND_LARK_DEFAULT_RECEIVE_ID`. An empty list
means the bot has not been added to any chat (§3.5) — not that the
credentials are wrong.

### Step 3 — real delivery

```bash
curl -s -X POST localhost:8000/api/notifications/test | jq
# {"results":[{"channel":"lark","status":"sent","external_ref":"om_dc13…","detail":null}]}
```

A card appears in the chat. To probe a different destination without
changing config:

```bash
curl -s -X POST 'localhost:8000/api/notifications/test?target=ou_abc123'   # a person
curl -s -X POST 'localhost:8000/api/notifications/test?target=dev@acme.com'
```

`status: "failed"` carries Lark's own error text in `detail` — and note the
incident pipeline would have continued anyway: a dead notification channel
is recorded, never raised
([notification_service.py](../apps/api/src/haaland/services/notification_service.py)).

### Without the API running

The same three checks, from a shell, touching neither Postgres nor Redis —
useful during first-time onboarding:

```bash
make lark-check          # steps 1 and 2
make lark-send           # steps 1, 2 and 3

# or directly, outside Docker:
cd apps/api && python scripts/lark_check.py --send --target oc_xxx
```

### Error decoder

| Symptom | Cause | Fix |
|---|---|---|
| `startup RuntimeError: … requires HAALAND_LARK_APP_ID` | `MODE=app`, credentials missing | §3.6 |
| `/lark/verify` → 502, `code=10003`/`10012` | wrong `app_id`/`app_secret`, or wrong `HAALAND_LARK_DOMAIN` | §3.1 |
| `/lark/verify` → 409 | `lark` missing from `NOTIFY_CHANNELS`, or `MODE=webhook` | §3.6 |
| verify passes, everything else fails | app version not released/approved by a Lark admin | §3.4 |
| `code 99991672` / permission denied | scope not granted, or granted but not re-released | §3.3 + §3.4 |
| send fails, `code 230002`-family | bot is not a member of that chat | §3.5 |
| webhook mode: `code 19021` "sign match fail" | `HAALAND_LARK_WEBHOOK_SECRET` mismatch | §2 step 3 |
| webhook mode: rejected with no obvious reason | keyword allowlist on the custom bot | disable it, or include the keyword |

---

## 5. Inbound callbacks (`POST /webhooks/lark/card`)

Needed only if you register a Request URL on the Lark app. Set it to
`{HAALAND_APP_BASE_URL}/webhooks/lark/card` under **Event Subscriptions**,
then copy that page's **Encrypt Key** and **Verification Token**:

```bash
HAALAND_LARK_ENCRYPT_KEY=…
HAALAND_LARK_VERIFICATION_TOKEN=…
```

Saving the Request URL makes Lark POST a `url_verification` challenge; the
endpoint answers it, which is what lets the console accept the URL. The
order is non-negotiable and identical to every other inbound webhook in
docs/04: **verify the signature against the raw bytes → decrypt → parse**.

Signature scheme (implemented in
[webhooks/signature.py](../apps/api/src/haaland/api/webhooks/signature.py),
`verify_lark_signature`): `sha256(timestamp + nonce + encrypt_key + raw_body)`,
constant-time compared, with a 5-minute replay window. Encrypted bodies are
AES-256-CBC with `key = sha256(encrypt_key)` and the IV in the first 16
bytes ([lark/crypto.py](../apps/api/src/haaland/integrations/notify/lark/crypto.py)).

Anything that is not a challenge — i.e. an actual card button tap —
currently returns **501**. See §6.

---

## 6. What is *not* implemented

- **Approve/Reject from a card button.** The card renders link buttons, not
  action buttons. Wiring a tap to the approval gate needs a
  `users.lark_open_id` column, role-based authorisation of the tapping user,
  an `approvals` row and the LangGraph resume — docs/11 §4 steps 3–8. Until
  that exists the endpoint returns 501 rather than accepting a tap that goes
  nowhere; approvals happen over `POST /api/incidents/{reference}/approve`.
- **Routing to code owners individually.** `CodeownersService` resolves
  GitHub logins; `LarkAppClient.open_ids_by_email` can map an email to an
  `open_id`, but nothing joins the two yet, so notifications go to the
  configured default destination.
- **In-place card updates on state change** ("Approved by @priya — merging").
  `LarkAppClient.update_card` exists and is tested; no caller stores the
  returned `message_id` on the incident yet.
- **Per-incident group chats** (docs/11 §4, `POST /open-apis/im/v1/chats`).

---

## 7. Where the code lives

```
apps/api/src/haaland/integrations/notify/
├── registry.py              config -> transport selection, fails fast
└── lark/
    ├── cards.py             NotificationMessage -> Lark card JSON (shared)
    ├── webhook_bot.py       custom-bot transport + its HMAC signing quirk
    ├── app_bot.py           tenant-app transport + receive_id type inference
    ├── client.py            Open Platform REST + tenant_access_token cache
    └── crypto.py            callback payload decryption

apps/api/src/haaland/api/routes/notifications.py    verify / chats / test
apps/api/src/haaland/api/webhooks/lark.py           inbound callback endpoint
apps/api/scripts/lark_check.py                      CLI verification
apps/api/tests/unit/test_lark_notifier.py           webhook transport
apps/api/tests/unit/test_lark_app.py                app transport + callbacks
```

Nothing outside `integrations/notify/lark/` knows Lark exists: the agent
nodes and services depend only on the `Notifier` Protocol in
[integrations/base.py](../apps/api/src/haaland/integrations/base.py).
