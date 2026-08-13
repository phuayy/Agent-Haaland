# haaland-api

FastAPI + LangGraph backend for Agent Haaland. See `../../docs/` for the
full architecture and `../../PLAN.md`-equivalent context in the repo root
docs for how this package fits together.

Quick start: `uv sync`, `docker compose up -d postgres redis` from the repo
root, `uv run alembic upgrade head`, then `uv run uvicorn haaland.main:app --reload`.
