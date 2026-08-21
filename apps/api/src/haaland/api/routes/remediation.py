"""GET .../remediation — the drafted fix(es): diff, PR link, risk notes. What
a reviewer needs to see before approving. Read-only mirror of the
`remediations` table, oldest attempt first."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.repositories.remediations import RemediationRepository
from haaland.db.session import get_session

router = APIRouter(prefix="/api/incidents", tags=["remediation"])


@router.get("/{reference}/remediation")
async def list_remediation_attempts(reference: str, session=Depends(get_session)) -> list[dict]:
    incident = await IncidentRepository(session).get_by_reference(reference)
    if incident is None:
        raise HTTPException(404, f"incident {reference} not found")
    rows = await RemediationRepository(session).list_for_incident(incident.id)
    return [
        {
            "strategy": r.strategy,
            "rationale": r.rationale,
            "risk_notes": r.risk_notes,
            "repo_full_name": r.repo_full_name,
            "branch_name": r.branch_name,
            "base_sha": r.base_sha,
            "patch": r.patch,
            "attempt_count": r.attempt_count,
            "pr_number": r.pr_number,
            "pr_url": r.pr_url,
            "status": r.status,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
        }
        for r in rows
    ]
