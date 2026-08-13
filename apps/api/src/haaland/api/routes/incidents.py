from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from haaland.api.deps import get_arq_pool
from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.session import get_session

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


async def _get_or_404(reference: str, session) -> object:
    incident = await IncidentRepository(session).get_by_reference(reference)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"incident {reference} not found")
    return incident


@router.get("")
async def list_incidents(session=Depends(get_session)) -> list[dict]:
    from sqlalchemy import select

    from haaland.db.models.incident import Incident

    rows = (
        await session.scalars(select(Incident).order_by(Incident.detected_at.desc()).limit(50))
    ).all()
    return [
        {
            "reference": r.reference,
            "title": r.title,
            "status": r.status,
            "severity": r.severity,
            "detected_at": r.detected_at,
            "closed_at": r.closed_at,
        }
        for r in rows
    ]


@router.get("/{reference}")
async def get_incident(reference: str, session=Depends(get_session)) -> dict:
    incident = await _get_or_404(reference, session)
    return {
        "reference": incident.reference,
        "title": incident.title,
        "status": incident.status,
        "severity": incident.severity,
        "severity_confidence": incident.severity_confidence,
        "repo_full_name": incident.repo_full_name,
        "root_cause_summary": incident.root_cause_summary,
        "detected_at": incident.detected_at,
        "closed_at": incident.closed_at,
    }


@router.post("/{reference}/approve")
async def approve_incident(
    reference: str,
    actor: str = "api",
    reason: str | None = None,
    session=Depends(get_session),
    arq_pool=Depends(get_arq_pool),
) -> dict:
    incident = await _get_or_404(reference, session)
    if incident.status != "awaiting_approval":
        raise HTTPException(422, f"incident is {incident.status}, not awaiting_approval")
    await arq_pool.enqueue_job(
        "resume_debug_session", str(incident.id), {"decision": "approve", "actor": actor, "reason": reason}
    )
    return {"status": "resuming"}


@router.post("/{reference}/reject")
async def reject_incident(
    reference: str,
    actor: str = "api",
    reason: str = "no reason given",
    session=Depends(get_session),
    arq_pool=Depends(get_arq_pool),
) -> dict:
    incident = await _get_or_404(reference, session)
    if incident.status != "awaiting_approval":
        raise HTTPException(422, f"incident is {incident.status}, not awaiting_approval")
    await arq_pool.enqueue_job(
        "resume_debug_session", str(incident.id), {"decision": "reject", "actor": actor, "reason": reason}
    )
    return {"status": "resuming"}
