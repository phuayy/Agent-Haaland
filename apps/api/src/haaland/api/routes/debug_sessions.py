"""The direct-input entrypoint (the plan's injection point): logs + a repo
URL in, a debug session enqueued out. Mirrors docs/04's five-step webhook
contract minus the signature step — this is an authenticated first-party
call, not a third-party webhook: validate, persist, enqueue, return fast."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from haaland.api.deps import get_arq_pool, get_deps
from haaland.api.schemas.debug_sessions import DebugSessionAccepted, DebugSessionCreate
from haaland.db.repositories.events import EventRepository
from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.session import session_scope
from haaland.integrations.scm.github import parse_repo_url
from haaland.services.audit_service import AuditService
from haaland.services.incident_service import IncidentService

router = APIRouter(prefix="/api/debug-sessions", tags=["debug-sessions"])


@router.post("", status_code=202, response_model=DebugSessionAccepted)
async def create_debug_session(
    body: DebugSessionCreate, deps=Depends(get_deps), arq_pool=Depends(get_arq_pool)
) -> DebugSessionAccepted:
    try:
        ref = parse_repo_url(body.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with session_scope() as session:
        audit = AuditService(EventRepository(session))
        incidents = IncidentRepository(session)
        incident_service = IncidentService(incidents, audit)
        incident = await incident_service.open_from_debug_session(
            service_name=body.service_name, repo_full_name=ref.full_name, base_ref=body.base_ref
        )
        incident_id = incident.id
        reference = incident.reference

    initial_state = {
        "incident_id": incident_id,
        "reference": reference,
        "service_name": body.service_name,
        "repo_url": body.repo_url,
        "repo_full_name": ref.full_name,
        "base_ref": body.base_ref,
        "log_text": body.log_text,
        "fix_attempt": 0,
        "check_reports": [],
        "errors": [],
        "cost_usd": 0.0,
    }

    await arq_pool.enqueue_job("run_debug_session", str(incident_id), initial_state)

    return DebugSessionAccepted(reference=reference, incident_id=str(incident_id), status="detected")
