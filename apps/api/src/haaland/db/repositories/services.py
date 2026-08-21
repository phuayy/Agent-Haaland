"""The service registry — the dashboard's list of monitored microservices.

The table has existed since migration 0001 but nothing wrote to it; the
frontend kept its own list in localStorage instead, which meant two browsers
saw two different registries and the backend could not link an incident to
the service it belongs to. Every read the dashboard performs now goes through
here.

Columns the registry needs but 0001 has no column for (the base branch to
patch, and the URL the operator typed) live in `metadata` rather than a new
migration — they are display/prefill values, never joined or filtered on.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.incident import Incident
from haaland.db.models.service import Service


class ServiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Service]:
        result = await self._session.scalars(select(Service).order_by(Service.name))
        return list(result)

    async def get(self, service_id: uuid.UUID) -> Service | None:
        return await self._session.get(Service, service_id)

    async def get_by_name(self, name: str) -> Service | None:
        return await self._session.scalar(select(Service).where(Service.name == name))

    async def create(
        self,
        *,
        name: str,
        repo_full_name: str | None = None,
        tier: int = 2,
        owner_team: str | None = None,
        runbook_url: str | None = None,
        base_ref: str = "main",
        repo_url: str | None = None,
    ) -> Service:
        row = Service(
            name=name,
            repo_full_name=repo_full_name,
            tier=tier,
            owner_team=owner_team,
            runbook_url=runbook_url,
            metadata_={"base_ref": base_ref, "repo_url": repo_url},
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_or_create_by_name(
        self, *, name: str, repo_full_name: str | None = None, base_ref: str = "main"
    ) -> Service:
        """Used by the ingest path so every incident lands attached to a
        service row, whether or not the operator registered it first — a
        debug session submitted straight to the API (curl, the Alertmanager
        webhook) still shows up on the dashboard."""
        existing = await self.get_by_name(name)
        if existing is not None:
            # A service registered before its first incident has no repo yet;
            # fill it from the run that supplied one rather than leaving the
            # card without a repo link.
            if existing.repo_full_name is None and repo_full_name is not None:
                existing.repo_full_name = repo_full_name
                await self._session.flush()
            return existing
        return await self.create(
            name=name,
            repo_full_name=repo_full_name,
            base_ref=base_ref,
            repo_url=f"https://github.com/{repo_full_name}" if repo_full_name else None,
        )

    async def list_incidents(self, service_id: uuid.UUID, *, limit: int = 50) -> list[Incident]:
        result = await self._session.scalars(
            select(Incident)
            .where(Incident.primary_service_id == service_id)
            .order_by(Incident.detected_at.desc())
            .limit(limit)
        )
        return list(result)

    async def list_incidents_for_all(self, *, limit: int = 500) -> list[Incident]:
        """One query for the whole registry — the list endpoint derives each
        card's health and counts from this in Python instead of firing a
        per-service query (N+1) or a window function the SQLite-less test
        setup would have to special-case."""
        result = await self._session.scalars(
            select(Incident)
            .where(Incident.primary_service_id.is_not(None))
            .order_by(Incident.detected_at.desc())
            .limit(limit)
        )
        return list(result)
