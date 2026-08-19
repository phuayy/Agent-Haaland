# Agent Haaland — Implementation Plan

Autonomous incident first-responder for core banking systems. **Detect → Diagnose → Document.**

This folder is the full engineering plan: architecture, technology choices with justified alternatives, data model, integration contracts, AI pipeline design, frontend spec, directory layout, and a phased roadmap.

## Read in this order

| # | Document | What's in it |
| --- | --- | --- |
| 00 | [Overview & Scope](00-overview.md) | Problem, product stages, prototype scope, explicit non-goals, success criteria |
| 01 | [Architecture](01-architecture.md) | Component diagram, end-to-end workflow diagram, incident state machine, sequence diagrams |
| 02 | [Technology Stack](02-tech-stack.md) | Every library choice with alternatives + reasoning. Includes the observability-platform bake-off |
| 03 | [Data Model](03-data-model.md) | Postgres schema DDL, the tamper-evident audit chain, retention policy |
| 04 | [Integrations](04-integrations.md) | Inbound/outbound webhook contracts, GitHub App, Slack, Jira, PagerDuty, adapter interfaces |
| 05 | [AI Pipeline](05-ai-pipeline.md) | PII masking + token vault, LangGraph state machine, prompts, model routing, cost model |
| 06 | [Frontend](06-frontend.md) | Pages, component inventory, realtime strategy, trace visualisation |
| 07 | [Directory Structure](07-directory-structure.md) | Full monorepo tree with rationale per directory |
| 08 | [Roadmap](08-roadmap.md) | 6 phases, each with deliverables and acceptance criteria |
| 09 | [Security & Compliance](09-security-compliance.md) | Threat model, prompt-injection defence, least-privilege, regulatory mapping |
| 10 | [Demo Script](10-demo-script.md) | The 5-minute demo, beat by beat, with the chaos commands that trigger it |
| 11 | [MVP Starter Plan](11-mvp-plan.md) | **Start here to build.** What to cut, what to build first, five milestones with runnable gates |
| 11 | [Monitoring Trigger & Lark](11-monitoring-trigger-integration.md) | Generic monitoring-platform ingestion contract, log compaction, Lark approval flow |
| 12 | [Setup & Integration Guide](12-setup-and-integration-guide.md) | Every setting, how to launch and verify, what is *actually* implemented |
| 13 | [Lark Integration](13-lark-integration.md) | Connecting a Lark organisation, both bot transports, step-by-step verification |

## The 60-second version

A fleet of instrumented demo banking microservices runs under Docker Compose alongside Prometheus, Loki, and Tempo. When a latency SLO burns or an error rate spikes, Alertmanager POSTs a webhook to the FastAPI backend. The backend correlates that signal with recent deploys (mirrored from GitHub webhooks), pulls the relevant logs and the offending trace, redacts PII into a reversible token vault, and hands a compact evidence bundle to Claude. Claude classifies severity (P1–P4), states a root cause with the evidence that supports it, and drafts a remediation. Nothing is applied automatically: the agent opens a pull request that stays pending, notifies the on-call engineer in Slack with approve/reject buttons, and records every step — machine and human — in an append-only, hash-chained timeline. When the incident closes, that timeline is already a post-mortem.

## Guiding principles

1. **The agent proposes, humans dispose.** No write path to production exists. The GitHub App has no merge permission by construction, not by policy.
2. **Everything is an event.** State is derived from an append-only log. The audit trail is not a feature bolted on at the end — it *is* the storage model.
3. **Logs are untrusted input.** Anything an attacker can write into a log line can reach the model. Structured output and a hard tool allowlist are the containment.
4. **One adapter interface per integration category.** Prometheus today, Datadog tomorrow, without touching the diagnosis engine.
5. **Demo determinism.** We must be able to break the system on cue and fix it on cue. That is why the observability stack is self-hosted for the prototype.
