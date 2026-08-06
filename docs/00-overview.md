# 00 — Overview & Scope

## The problem, stated precisely

In a bank's production estate, the expensive part of an incident is rarely the fix. It is the twenty minutes between "something is wrong" and "we know which service, which deploy, and who owns it," plus the two hours afterwards spent reconstructing what happened for the regulator.

Three costs compound:

1. **Detection lag.** The first signal is often a customer complaint or an engineer noticing a dashboard, not an alert that fired into someone's hands with context attached.
2. **Diagnosis toil.** Correlating a latency spike to a config change made forty minutes ago requires a human to hold five browser tabs — APM, logs, traces, the deploy pipeline, and the on-call rota — in their head simultaneously.
3. **Documentation debt.** Under MAS TRM, RBI, PCI-DSS, and DORA, undocumented downtime is a reportable control failure. Post-mortems get written days later from memory and Slack scrollback, which makes them both inaccurate and expensive.

Agent Haaland attacks all three by treating an incident as a **workflow with a durable state machine** rather than a chat transcript.

## The four stages

### 1. Detect & Trace

Continuous monitoring of microservice pods. On an abnormal latency spike or service failure, the agent:

- Identifies the affected service and the blast radius (which downstream services degraded).
- Retrieves the relevant log window, filtered to the error signature.
- Pulls the exemplar trace and renders a visual tracing map showing where the time went.
- Gathers surrounding context: recent Git deployments, infrastructure changes, config updates, and the dependency graph.

### 2. Safe AI Triage

Before any text reaches the model:

- Account numbers, IBANs, card PANs, national IDs, emails, phone numbers, and customer names are replaced with stable tokens (`<ACCOUNT_1>`, `<PAN_3>`). The mapping lives in an encrypted, short-TTL vault that the model never sees.
- The model classifies severity into P1–P4 with an explicit rationale and a confidence score.
- **P3/P4** → a Jira ticket is filed with the evidence attached and the incident is parked.
- **P1/P2** → the on-call engineer is paged immediately, and remediation drafting begins.

This is the mechanism that stops engineers drowning in noise: only genuinely severe things interrupt a human.

### 3. Human-in-the-Loop Remediation

The agent drafts a remediation — typically a revert to the last known-good deployment, or a configuration restore (e.g. putting a database connection pool size back). It:

- Opens a **pull request that cannot self-merge.**
- Posts to the incident Slack channel with the evidence bundle, the diff, and Approve / Reject / Request-changes buttons.
- Pulls in the relevant stakeholders based on CODEOWNERS and service registry ownership.
- Blocks. The workflow is genuinely suspended — not polling, not a timeout — until a human decides.

### 4. Document & Harden

On recovery:

- A regression test is generated from the exact failure scenario, so the same bug cannot reach production silently again.
- The post-mortem is *assembled*, not written: the alert, the deploy history, the root cause, AI recommendations, approvals, the rollback, and every human decision are already in the timeline with timestamps and actors. Rendering it is a template application.
- Export to PDF and Markdown for compliance filing.

The critical design consequence: **documentation is generated continuously during the incident, not reconstructed after it.**

## Prototype scope

What ships in the prototype, in priority order:

| In scope | Notes |
| --- | --- |
| Self-hosted observability stack + 5 fake banking microservices | Docker Compose. Breakable on demand. |
| Alertmanager → backend webhook ingestion | The detection trigger |
| GitHub App webhooks for deploy history | `push`, `deployment_status`, `workflow_run`, `pull_request` |
| Log retrieval from Loki, trace retrieval from Tempo | Time-windowed, signature-filtered |
| PII redaction with a reversible token vault | Presidio + custom banking recognisers |
| Claude-driven triage, root-cause, and remediation drafting | Structured output, no free-text parsing |
| GitHub PR drafting on a branch, never merged | Least-privilege App install |
| Slack notification with interactive approval | Signature-verified interaction endpoint |
| Jira ticket creation for low-severity | Adapter also supports Linear |
| Append-only, hash-chained incident timeline | The compliance artefact |
| Regression test generation | pytest for Python services |
| Post-mortem generation and export | Markdown + PDF |
| Next.js dashboard | Live incident feed, trace map, timeline, approval UI |

## Explicit non-goals for the prototype

Stating these prevents scope creep and makes the demo honest.

- **No auto-remediation.** Ever. Not behind a flag, not in "trusted mode." The absence of a production write path is the product's core safety claim.
- **No multi-tenancy.** Single bank, single workspace. Row-level tenancy is a schema concern deferred to Phase 6.
- **No SSO/SAML.** Session auth with a seeded user table. Real deployments need SAML + SCIM; that is integration work, not architecture work.
- **No Kubernetes operator.** Docker Compose models pods well enough to demonstrate the concept. A real deployment would watch the K8s API for pod events.
- **No log ingestion at bank scale.** We query Loki on demand rather than streaming and indexing everything ourselves.
- **No fine-tuned models.** Prompting plus structured output plus retrieval over runbooks is sufficient and far more auditable.

## Success criteria for the prototype

The prototype succeeds if, on a cold start, a single chaos command produces all of the following without human intervention:

1. An incident appears in the dashboard within **30 seconds** of the fault being injected.
2. The incident names the correct service and the correct culprit deployment.
3. A trace map renders showing the latency concentrated in the right span.
4. The severity classification matches the injected fault class.
5. A pull request exists on GitHub with a diff that would actually fix the fault.
6. A Slack message with working approve/reject buttons has been posted.
7. Approving in Slack transitions the incident state and appends an audit event naming the approver.
8. The generated post-mortem contains a correct, chronologically ordered timeline with no manual editing.
9. No unredacted account number appears anywhere in the AI request logs.

## Users

| Persona | What they need | Where they live in the product |
| --- | --- | --- |
| **On-call SRE** | Wake up to context, not a pager code. Decide in under a minute. | Slack approval card; incident detail page |
| **Service owner / dev** | Understand what their deploy did; review the drafted revert. | GitHub PR; trace map |
| **Engineering manager** | See MTTD/MTTR trending, which services are noisy. | Dashboard overview |
| **Compliance / risk officer** | An immutable, exportable record proving controls operated. | Timeline export, post-mortem PDF, audit log verification page |
