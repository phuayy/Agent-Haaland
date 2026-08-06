# 10 — Demo Script

Five minutes, one injected fault, no slides after the first. The demo is the product.

---

## The scenario

At 09:12, a developer merged a "performance tuning" change to `ledger-service` that reduced the database connection pool from 50 to 5. Traffic is normal. Within ninety seconds the pool saturates, `ledger-service` begins queueing, `payments-api` times out waiting on it, and customers cannot complete transfers.

This scenario is chosen deliberately:

- **It is boringly realistic.** Every engineer in the room has caused or debugged exactly this.
- **The root cause is not where the alert fires.** The alert is on `payments-api`; the fault is in `ledger-service`. This is the thing humans are slow at and the agent is fast at.
- **The fix is a one-line revert**, so the drafted PR is small enough to read on screen.
- **It requires correlating four sources** — metric shape, log signature, trace waterfall, and a Git diff. That is the whole value proposition in one fault.

---

## Before you start

```bash
make up            # full stack
make seed          # migrations, service registry, users, demo repo
# leave the load generator running for 5+ minutes so baselines exist
make reset         # confirm everything is green
```

Have four windows ready:

1. Browser — Agent Haaland dashboard at `/incidents` (empty, green)
2. Browser tab — Slack, `#incidents` channel
3. Browser tab — GitHub, the demo repo's Pull Requests page
4. Terminal — for the chaos command

Pre-flight checklist:

- [ ] `/incidents` shows the all-clear empty state, 5 services monitored
- [ ] Slack app installed, interactivity URL pointing at your tunnel
- [ ] GitHub App installed, branch protection on `main` visible
- [ ] `make chaos-pool` has been rehearsed once and `make reset` has cleaned up
- [ ] `ANTHROPIC_API_KEY` has budget
- [ ] Tunnel is live (`cloudflared` / `ngrok`)

---

## The run

### Beat 0 — The setup (30 seconds)

> "This is a bank's payment estate. Five microservices, healthy. Nobody is looking at this dashboard, and that's the point — Agent Haaland watches so nobody has to."

Show `/incidents`: green, empty, "no active incidents, last incident 4 days ago."

Show `/services`: the dependency graph, all nodes green.

### Beat 1 — Detect (60 seconds)

Run the fault. Say what you're doing as you do it:

```bash
make chaos-pool
```

> "I've just merged a change that drops the ledger service's database connection pool from 50 to 5. This is a real commit, pushed to a real repository. Nothing else changes. Traffic is normal."

**Do not touch the dashboard.** Let it update itself. Within roughly 60–90 seconds:

1. A toast appears: **New incident detected**.
2. A red row slides into the feed: `INC-2026-0042 — payments-api elevated latency`, status `enriching`.
3. Watch the status badge move: `enriching` → `triaging` → `diagnosing`.

> "No human did anything. Prometheus fired, Alertmanager posted a webhook, and the agent is already pulling logs, traces, and deployment history in parallel."

Click into the incident.

### Beat 2 — Trace (60 seconds)

Go to the **Trace** tab.

The service map renders. `api-gateway` and `payments-api` are amber. `ledger-service` is red, ringed, with a red commit badge.

> "The alert fired on `payments-api`. But look — the agent has traced through the call graph. The latency isn't in payments. It's downstream, in the ledger service. And it's flagged that service as deployed eleven minutes ago."

Scroll to the span waterfall.

> "Here's a single slow request. Four point two seconds. The gateway spent almost nothing. Payments spent almost nothing of its own time. Three point nine seconds is sitting *inside* one ledger span, waiting on a database connection."

Point at the self-time shading. This is the moment the audience understands the product.

### Beat 3 — Safe triage (45 seconds)

Back to the **Overview** tab. Expand the **Logs** evidence section.

> "Before any of this reached the AI, it was sanitised."

Point at the redacted values in the log excerpt:

```
2026-08-06T09:11:47Z ERROR ledger-service TimeoutError: pool exhausted
  acquiring connection for account <ACCOUNT_1>, customer <CUSTOMER_ID_3>
  (1847 occurrences, first 09:11:47, last 09:13:22)
```

> "Account numbers, customer IDs, emails — replaced with tokens before the request left our boundary. The model never saw a real account number. The mapping is encrypted, in memory, expires in 24 hours, and it's audited every time a human reveals one."

Click a masked chip to reveal, then point out that the reveal itself just wrote an audit event.

> "Also note: 1,847 occurrences, collapsed into one line. We don't paste 500 log lines into a prompt. We group by error signature. It's ten times cheaper and it diagnoses better."

Now the root cause card.

> "P1. Ninety-one percent confidence. And here's the root cause."

Read it aloud:

> *"Deploy `a3f91c2` to ledger-service reduced `DB_POOL_SIZE` from 50 to 5. The pool saturated at 09:11:47 under normal traffic. Ledger began queueing connection acquisitions, and payments-api exhausted its client timeout waiting on ledger, cascading to customer-facing transfer failures."*

> "Every claim there is linked to evidence." — expand `Supporting evidence` and show the three citations, each linking back to Loki, Tempo, and the GitHub diff.

Optionally open the **Show AI reasoning** disclosure.

> "And this is auditable. Model, prompt version, tokens, cost — sixty-one cents for this whole incident."

### Beat 4 — Human in the loop (75 seconds)

Switch to Slack.

The card is there: red P1 header, incident reference, detection time, confidence, suspect commit, root cause, and three buttons.

> "The on-call engineer got this. Not a pager code — the actual diagnosis, with the evidence, and a decision to make."

Switch to GitHub, Pull Requests. PR #217 is open, labelled `incident`, `automated`, `needs-review`.

> "The agent has already drafted the fix."

Open the PR. Show the one-line diff restoring `DB_POOL_SIZE: 50`.

**Now the most important line in the demo:**

> "And this is where it stops. Agent Haaland has no path to production. It cannot merge this. Not because we told it not to — because the GitHub App doesn't have that capability, and branch protection requires a human review from a code owner. If this agent were completely compromised, the worst it could do is open a pull request."

Show the branch protection settings if you have them to hand.

Back to Slack. Click **Approve rollback**. The confirmation dialog appears.

> "Second intent capture, because this authorises a production change."

Confirm. The card updates to `Approved by @priya — 09:16:41`.

Switch to the dashboard: the incident status has already moved to `approved`. Nobody refreshed anything.

**Optional, if the audience is technical — this lands hard:**

```bash
docker compose kill worker && docker compose up -d worker
```

> "I just killed the process running the workflow, mid-incident, and restarted it. Watch."

Approve in Slack. It resumes at exactly the right step.

> "The workflow state is checkpointed in Postgres. Incidents last hours. Your deploys shouldn't lose them."

### Beat 5 — Document (60 seconds)

Merge the PR in GitHub. Deploy runs.

Back on the dashboard: `remediating` → `verifying`. The agent is polling Prometheus.

> "It's confirming the fix actually worked — three consecutive healthy samples before it will claim recovery."

Status flips to `documenting`, then `closed`.

Go to the **Timeline** tab.

> "Here is what the agent has been doing the entire time we were talking."

Green banner: **Audit chain verified — 31 events, unbroken**.

Scroll the timeline slowly. Point at the actor icons.

> "Every action. System, AI, human — attributed, timestamped, and hash-chained. This isn't a log we write alongside the state. It *is* the state. And Priya's approval is in there, with her name, the time, and the channel she approved from."

Go to the **Post-mortem** tab.

> "And that means the post-mortem was never written. It was assembled — from data that already existed, the moment the incident closed."

Scroll: summary, impact, timeline table, root cause, resolution, human decisions, action items.

Click **Export PDF**.

> "In banking, an undocumented outage isn't an engineering problem — it's a reportable control failure. MAS wants an initial report inside an hour. This was ready in four minutes, and nobody wrote it."

### Beat 6 — Close (20 seconds)

> "Detect. Diagnose. Document. Eleven minutes from a bad merge to a documented, approved, verified fix — and the only thing a human did was read one Slack card and click Approve."

Optional final beat, if it lands: show the regression test PR.

> "It also wrote the test that stops this recurring."

---

## Timing

| Beat | Target | Cumulative |
|---|---|---|
| 0 Setup | 0:30 | 0:30 |
| 1 Detect | 1:00 | 1:30 |
| 2 Trace | 1:00 | 2:30 |
| 3 Safe triage | 0:45 | 3:15 |
| 4 Human in the loop | 1:15 | 4:30 |
| 5 Document | 1:00 | 5:30 |
| 6 Close | 0:20 | 5:50 |

Beat 1's dead air while the agent works is the demo's biggest risk. Fill it by narrating what is happening under the hood — that dead air is actually the strongest proof that nothing is scripted.

---

## Failure recovery during a live demo

| It breaks | Do this |
|---|---|
| Alert doesn't fire in 90s | `make chaos-pool` is idempotent — run it again while narrating the alert rule. Have a pre-recorded incident at `/incidents/INC-2026-0001` as the fallback. |
| Claude is slow or rate-limited | Keep a completed incident open in a background tab. Say "I'll show you one from earlier while this finishes." Do not apologise; it happens to every live demo. |
| Slack interaction fails | Approve from the dashboard's `/remediation` tab instead — it is the same code path, and demonstrating both channels is a feature, not a save. |
| Tunnel drops | GitHub and Slack die but the core loop does not. Detection, diagnosis, and the timeline all still work over the internal network. Pivot to the audit/post-mortem story. |
| The trace map is empty | Tempo search is the flakiest dependency. Keep a saved trace ID and a direct link. |

**Always run `make reset` between rehearsals** and confirm the feed is green before starting. A leftover amber service undermines Beat 0.

---

## The three sentences to make sure you say

If everything else goes wrong, these are the claims that differentiate the product:

1. **"The alert fired on payments, but the fault was in ledger — and it found that in ninety seconds by correlating four different systems."**
2. **"The model never saw a real account number, and it cannot merge to production. Not by policy — by construction."**
3. **"The post-mortem wasn't written. It was assembled from an append-only, tamper-evident record that was being built the entire time the incident was happening."**
