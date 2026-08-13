"""AsyncPostgresSaver setup. `thread_id = incident_id` is the whole trick
(docs/05) — the incident *is* the LangGraph conversation thread, so killing
and restarting the worker mid-approval resumes at the exact suspended node."""

from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from haaland.config import Settings


@asynccontextmanager
async def build_checkpointer(settings: Settings):
    conn_string = str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        await saver.setup()
        yield saver
