from __future__ import annotations

from fastapi import APIRouter

from haaland.api.routes import audit, debug_sessions, incidents, notifications, postmortems
from haaland.api.webhooks import alertmanager, github, lark

api_router = APIRouter()

for router in (
    debug_sessions.router,
    incidents.router,
    audit.router,
    postmortems.router,
    notifications.router,
    alertmanager.router,
    github.router,
    lark.router,
):
    api_router.include_router(router)
