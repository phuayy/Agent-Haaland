"""The direct-input entrypoint (the plan's injection point): logs + a repo
URL in, a debug session enqueued out. Mirrors docs/04's five-step webhook
contract minus the signature step — this is an authenticated first-party
call, not a third-party webhook: validate, persist, enqueue, return fast.

The persist-and-enqueue half lives in api/ingest.py because the
Alertmanager webhook creates sessions through exactly the same path."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from haaland.api.deps import get_arq_pool
from haaland.api.ingest import launch_debug_session
from haaland.api.schemas.debug_sessions import DebugSessionAccepted, DebugSessionCreate

router = APIRouter(prefix="/api/debug-sessions", tags=["debug-sessions"])


@router.post("", status_code=202, response_model=DebugSessionAccepted)
async def create_debug_session(
    body: DebugSessionCreate, arq_pool=Depends(get_arq_pool)
) -> DebugSessionAccepted:
    try:
        reference, incident_id = await launch_debug_session(body, arq_pool)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DebugSessionAccepted(reference=reference, incident_id=incident_id, status="detected")
