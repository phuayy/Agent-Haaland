from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from haaland.domain.health import Health


class ServiceCreate(BaseModel):
    """What the dashboard's "Add Service" form posts.

    `repo_url` is the full URL the operator pasted; the route parses it to the
    `owner/repo` the rest of the system speaks (integrations/scm/github.py)
    and rejects anything unparseable with a 422, so a typo surfaces at
    registration instead of at the first debug session.
    """

    name: str = Field(min_length=1, max_length=200)
    repo_url: str | None = Field(default=None, max_length=500)
    base_ref: str = Field(default="main", max_length=200)
    tier: int = Field(default=2, ge=1, le=3)
    owner_team: str | None = Field(default=None, max_length=200)
    runbook_url: str | None = Field(default=None, max_length=500)


class ServiceIncidentSummary(BaseModel):
    reference: str
    title: str
    status: str
    severity: str | None
    detected_at: datetime
    closed_at: datetime | None


class ServiceRead(BaseModel):
    id: str
    name: str
    repo_full_name: str | None
    repo_url: str | None
    base_ref: str
    tier: int
    owner_team: str | None
    runbook_url: str | None
    created_at: datetime
    # Derived per request from the incident table — see domain/health.py.
    health: Health
    incident_count: int
    active_incident_count: int
    last_incident: ServiceIncidentSummary | None
