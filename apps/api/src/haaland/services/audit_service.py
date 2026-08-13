from __future__ import annotations

import uuid

from haaland.db.repositories.events import EventRepository
from haaland.domain.enums import ActorType


class AuditService:
    """Thin wrapper so callers depend on a service, not a repository —
    repositories are a db/ concern, services are the framework-free layer
    the agent nodes are allowed to call directly."""

    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def record(
        self,
        incident_id: uuid.UUID,
        event_type: str,
        *,
        actor_type: ActorType,
        actor_label: str,
        summary: str,
        payload: dict | None = None,
        actor_id: str | None = None,
    ) -> None:
        await self._events.append(
            incident_id=incident_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_label=actor_label,
            summary=summary,
            payload=payload,
            actor_id=actor_id,
        )

    async def verify(self, incident_id: uuid.UUID) -> dict:
        return await self._events.verify_chain(incident_id)

    async def timeline(self, incident_id: uuid.UUID) -> list:
        return await self._events.list_for_incident(incident_id)
