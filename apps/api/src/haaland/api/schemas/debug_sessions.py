from __future__ import annotations

from pydantic import BaseModel

from haaland.domain.models import DebugSessionRequest


class DebugSessionAccepted(BaseModel):
    reference: str
    incident_id: str
    status: str


class DebugSessionCreate(DebugSessionRequest):
    """Same shape as the domain contract — kept as a distinct class per
    docs/07's "schemas != domain models" so the API's wire contract can
    diverge later (e.g. multipart log file upload) without touching the
    domain type the graph actually consumes."""
