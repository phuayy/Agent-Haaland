from __future__ import annotations

from fastapi import APIRouter

from haaland.api.routes import audit, debug_sessions, incidents, postmortems
from haaland.api.webhooks import alertmanager, github

api_router = APIRouter()

for router in (
    debug_sessions.router,
    incidents.router,
    audit.router,
    postmortems.router,
    alertmanager.router,
    github.router,
):
    api_router.include_router(router)
