"""GET .../audit/verify is the compliance artefact's self-check — walks the
chain and recomputes every hash (docs/03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from haaland.db.repositories.events import EventRepository
from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.session import get_session

router = APIRouter(prefix="/api/incidents", tags=["audit"])


@router.get("/{reference}/audit")
async def get_timeline(reference: str, session=Depends(get_session)) -> list[dict]:
    incident = await IncidentRepository(session).get_by_reference(reference)
    if incident is None:
        raise HTTPException(404, f"incident {reference} not found")
    events = await EventRepository(session).list_for_incident(incident.id)
    return [
        {
            "seq": e.seq,
            "event_type": e.event_type,
            "actor_type": e.actor_type,
            "actor_label": e.actor_label,
            "summary": e.summary,
            "occurred_at": e.occurred_at,
        }
        for e in events
    ]


@router.get("/{reference}/audit/verify")
async def verify_chain(reference: str, session=Depends(get_session)) -> dict:
    incident = await IncidentRepository(session).get_by_reference(reference)
    if incident is None:
        raise HTTPException(404, f"incident {reference} not found")
    return await EventRepository(session).verify_chain(incident.id)
