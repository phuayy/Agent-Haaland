from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from haaland.db.models.postmortem import Postmortem
from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.session import get_session

router = APIRouter(prefix="/api/incidents", tags=["postmortems"])


@router.get("/{reference}/postmortem")
async def get_postmortem(reference: str, as_markdown: bool = False, session=Depends(get_session)):
    incident = await IncidentRepository(session).get_by_reference(reference)
    if incident is None:
        raise HTTPException(404, f"incident {reference} not found")

    row = await session.scalar(select(Postmortem).where(Postmortem.incident_id == incident.id))
    if row is None:
        raise HTTPException(404, "postmortem not yet generated")

    if as_markdown:
        return Response(content=row.markdown, media_type="text/markdown")
    return {"version": row.version, "markdown": row.markdown, "generated_at": row.generated_at}
