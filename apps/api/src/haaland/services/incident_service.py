from __future__ import annotations

import uuid

from haaland.db.repositories.incidents import IncidentRepository
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.state_machine import assert_legal
from haaland.services.audit_service import AuditService


class IncidentService:
    def __init__(self, incidents: IncidentRepository, audit: AuditService) -> None:
        self._incidents = incidents
        self._audit = audit

    async def open_from_debug_session(
        self, *, service_name: str, repo_full_name: str, base_ref: str
    ):
        reference = await self._incidents.next_reference()
        incident = await self._incidents.create(
            reference=reference,
            title=f"Debug session — {service_name}",
            repo_full_name=repo_full_name,
            base_ref=base_ref,
        )
        await self._audit.record(
            incident.id,
            "debug_session.submitted",
            actor_type=ActorType.HUMAN,
            actor_label="api",
            summary=f"Debug session submitted for {service_name} ({repo_full_name}@{base_ref})",
            payload={"service_name": service_name, "repo_full_name": repo_full_name, "base_ref": base_ref},
        )
        return incident

    async def transition(
        self,
        incident_id: uuid.UUID,
        target: IncidentStatus,
        *,
        actor_type: ActorType,
        actor_label: str,
        summary: str,
        event_type: str,
        payload: dict | None = None,
    ) -> None:
        incident = await self._incidents.get(incident_id)
        if incident is None:
            raise LookupError(f"incident {incident_id} not found")
        assert_legal(IncidentStatus(incident.status), target)
        await self._incidents.set_status(incident_id, target)
        await self._audit.record(
            incident_id,
            event_type,
            actor_type=actor_type,
            actor_label=actor_label,
            summary=summary,
            payload=payload,
        )
