"""Application factory. HTTP handlers stay thin — verify, persist, enqueue —
the actual incident workflow runs in the worker process (worker.py) so a
webhook handler never blocks on 20-90 seconds of evidence collection plus
LLM calls (docs/01's "why a worker process at all")."""

from __future__ import annotations

from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from haaland.agent.checkpointer import build_checkpointer
from haaland.agent.graph import build_graph
from haaland.api.router import api_router
from haaland.config import get_settings
from haaland.db.session import init_engine
from haaland.deps import build_deps
from haaland.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(json=settings.is_prod)
    init_engine(settings)

    deps = build_deps(settings)
    app.state.deps = deps
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(str(settings.redis_url)))

    async with build_checkpointer(settings) as checkpointer:
        app.state.graph = build_graph(deps, checkpointer)
        logger.info("startup complete", env=settings.env, llm_provider=settings.llm_provider)
        yield

    await app.state.arq_pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Haaland", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
