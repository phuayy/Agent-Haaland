"""GET .../evidence — what the agent actually collected before diagnosing.
Read-only mirror of the `evidence` table; nothing here is computed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from haaland.db.repositories.evidence import EvidenceRepository
from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.session import get_session

router = APIRouter(prefix="/api/incidents", tags=["evidence"])


@router.get("/{reference}/evidence")
async def list_evidence(reference: str, session=Depends(get_session)) -> list[dict]:
    incident = await IncidentRepository(session).get_by_reference(reference)
    if incident is None:
        raise HTTPException(404, f"incident {reference} not found")
    rows = await EvidenceRepository(session).list_for_incident(incident.id)
    return [
        {
            "kind": e.kind,
            "source": e.source,
            "source_ref": e.source_ref,
            "content": e.content,
            "relevance": e.relevance,
            "collected_at": e.collected_at,
        }
        for e in rows
    ]
