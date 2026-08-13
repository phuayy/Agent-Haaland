"""FastAPI-layer dependencies — thin accessors onto app.state plus the (as
yet unimplemented) auth guards. docs/00 explicitly defers real auth to a
seeded user table with session cookies; `current_user` here is a placeholder
identity until that lands, kept isolated to this one module so wiring real
auth later touches one file."""

from __future__ import annotations

from arq import ArqRedis
from fastapi import Request

from haaland.deps import Deps


def get_deps(request: Request) -> Deps:
    return request.app.state.deps


def get_graph(request: Request):
    return request.app.state.graph


def get_arq_pool(request: Request) -> ArqRedis:
    return request.app.state.arq_pool


def current_user(request: Request) -> str:
    """Placeholder identity — docs/00 non-goal: "Session auth with a seeded
    user table" is integration work not yet built. Every actor label is
    "api" until it lands."""
    return request.headers.get("X-Haaland-Actor", "api")
