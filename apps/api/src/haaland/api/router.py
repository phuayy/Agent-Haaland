from __future__ import annotations

from fastapi import APIRouter, Depends

from haaland.api.routes import (
    audit,
    debug_sessions,
    evidence,
    incidents,
    notifications,
    postmortems,
    remediation,
    services,
)
from haaland.api.security import require_api_auth
from haaland.api.webhooks import alertmanager, github, lark

api_router = APIRouter()

# First-party /api routes: bearer-token auth (api/security.py).
for router in (
    debug_sessions.router,
    incidents.router,
    services.router,
    audit.router,
    evidence.router,
    remediation.router,
    postmortems.router,
    notifications.router,
):
    api_router.include_router(router, dependencies=[Depends(require_api_auth)])

# Webhooks: exempt from the API token — each verifies its own upstream
# signature (bearer / HMAC / Lark scheme) against the raw body instead.
for router in (alertmanager.router, github.router, lark.router):
    api_router.include_router(router)
