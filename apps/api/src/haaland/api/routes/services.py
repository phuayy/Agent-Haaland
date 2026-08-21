"""The service registry the dashboard renders.

Until now the frontend kept this list in localStorage (apps/web
src/lib/store.ts) with a hardcoded seed, so the "services" a demo showed were
whatever that browser profile happened to hold and no service could be linked
to the incidents run against it. These endpoints move the registry into the
`services` table that migration 0001 already created, and derive each card's
health from live incident rows instead of the browser's memory of what it
triggered.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from haaland.api.schemas.services import ServiceCreate, ServiceIncidentSummary, ServiceRead
from haaland.db.models.incident import Incident
from haaland.db.models.service import Service
from haaland.db.repositories.services import ServiceRepository
from haaland.db.session import get_session
from haaland.domain.health import derive_health, is_active
from haaland.integrations.scm.github import parse_repo_url

router = APIRouter(prefix="/api/services", tags=["services"])


def _incident_summary(incident: Incident) -> ServiceIncidentSummary:
    return ServiceIncidentSummary(
        reference=incident.reference,
        title=incident.title,
        status=incident.status,
        severity=incident.severity,
        detected_at=incident.detected_at,
        closed_at=incident.closed_at,
    )


def _to_read(service: Service, incidents: list[Incident]) -> ServiceRead:
    """`incidents` must arrive newest-first — the repository orders by
    detected_at desc and this takes [0] as the latest."""
    metadata = service.metadata_ or {}
    return ServiceRead(
        id=str(service.id),
        name=service.name,
        repo_full_name=service.repo_full_name,
        repo_url=metadata.get("repo_url")
        or (f"https://github.com/{service.repo_full_name}" if service.repo_full_name else None),
        base_ref=metadata.get("base_ref") or "main",
        tier=service.tier,
        owner_team=service.owner_team,
        runbook_url=service.runbook_url,
        created_at=service.created_at,
        health=derive_health([(i.status, i.severity) for i in incidents]),
        incident_count=len(incidents),
        active_incident_count=sum(1 for i in incidents if is_active(i.status)),
        last_incident=_incident_summary(incidents[0]) if incidents else None,
    )


async def _get_or_404(service_id: str, session) -> Service:
    try:
        parsed = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(404, f"service {service_id} not found") from None
    service = await ServiceRepository(session).get(parsed)
    if service is None:
        raise HTTPException(404, f"service {service_id} not found")
    return service


@router.get("", response_model=list[ServiceRead])
async def list_services(session=Depends(get_session)) -> list[ServiceRead]:
    repo = ServiceRepository(session)
    services = await repo.list_all()
    by_service: dict[uuid.UUID, list[Incident]] = defaultdict(list)
    for incident in await repo.list_incidents_for_all():
        by_service[incident.primary_service_id].append(incident)
    return [_to_read(service, by_service.get(service.id, [])) for service in services]


@router.post("", status_code=201, response_model=ServiceRead)
async def create_service(body: ServiceCreate, session=Depends(get_session)) -> ServiceRead:
    repo_full_name, repo_url = None, None
    if body.repo_url:
        try:
            repo_full_name = parse_repo_url(body.repo_url).full_name
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        # Store the canonical form, not the string as typed: a pasted clone
        # URL ends in .git, which is wrong in the card's browser link.
        repo_url = f"https://github.com/{repo_full_name}"

    repo = ServiceRepository(session)
    if await repo.get_by_name(body.name) is not None:
        raise HTTPException(409, f"a service named {body.name!r} is already registered")

    try:
        service = await repo.create(
            name=body.name,
            repo_full_name=repo_full_name,
            tier=body.tier,
            owner_team=body.owner_team,
            runbook_url=body.runbook_url,
            base_ref=body.base_ref or "main",
            repo_url=repo_url,
        )
    except IntegrityError as exc:
        # Two operators registering the same name at once lose the race on the
        # unique constraint rather than on the check above.
        raise HTTPException(409, f"a service named {body.name!r} is already registered") from exc

    return _to_read(service, [])


@router.get("/{service_id}", response_model=ServiceRead)
async def get_service(service_id: str, session=Depends(get_session)) -> ServiceRead:
    service = await _get_or_404(service_id, session)
    incidents = await ServiceRepository(session).list_incidents(service.id)
    return _to_read(service, incidents)


@router.get("/{service_id}/incidents", response_model=list[ServiceIncidentSummary])
async def list_service_incidents(
    service_id: str, session=Depends(get_session)
) -> list[ServiceIncidentSummary]:
    service = await _get_or_404(service_id, session)
    incidents = await ServiceRepository(session).list_incidents(service.id)
    return [_incident_summary(i) for i in incidents]
