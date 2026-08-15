from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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


class ApprovalRequest(BaseModel):
    """Body, not query params — an approval is a state-changing action and
    its actor/reason belong in the request body, not in access logs and
    proxy caches by way of the URL."""

    actor: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)


class RejectionRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    # docs/08 Phase 3: a rejection without a reason is not actionable —
    # the reason is fed back into the re-draft loop as model input.
    reason: str = Field(min_length=3, max_length=2000)


async def _resume(reference: str, session, arq_pool, decision: dict) -> dict:
    incident = await _get_or_404(reference, session)
    if incident.status != "awaiting_approval":
        raise HTTPException(422, f"incident is {incident.status}, not awaiting_approval")
    await arq_pool.enqueue_job("resume_debug_session", str(incident.id), decision)
    return {"status": "resuming"}


@router.post("/{reference}/approve")
async def approve_incident(
    reference: str,
    body: ApprovalRequest,
    session=Depends(get_session),
    arq_pool=Depends(get_arq_pool),
) -> dict:
    return await _resume(
        reference, session, arq_pool,
        {"decision": "approve", "actor": body.actor, "reason": body.reason, "channel": "api"},
    )


@router.post("/{reference}/reject")
async def reject_incident(
    reference: str,
    body: RejectionRequest,
    session=Depends(get_session),
    arq_pool=Depends(get_arq_pool),
) -> dict:
    return await _resume(
        reference, session, arq_pool,
        {"decision": "reject", "actor": body.actor, "reason": body.reason, "channel": "api"},
    )
