# haaland-api

FastAPI + LangGraph backend for Agent Haaland. See `../../docs/` for the
full architecture and `../../PLAN.md`-equivalent context in the repo root
docs for how this package fits together.

This package is a **uv workspace member**. The lockfile and the virtualenv
live at the repo root — there is no `uv.lock` in this directory, and
`uv sync` run from here resolves to the root environment.

Quick start, from the repo root:

```bash
uv sync                                  # one venv for the whole workspace
docker compose up -d postgres redis
cd apps/api
uv run alembic upgrade head
uv run uvicorn haaland.main:app --reload # terminal 1
uv run arq haaland.worker.WorkerSettings # terminal 2 — not optional
```

Optional extras: `uv sync --extra presidio` (ML-assisted PII analysis) and
`uv sync --extra pdf` (WeasyPrint post-mortem rendering). `openai` is a
required dependency, not an extra — the default provider (deepseek) speaks
the OpenAI-compatible wire format through that SDK.
