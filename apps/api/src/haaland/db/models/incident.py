from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base
from haaland.domain.enums import IncidentStatus, Severity

incident_status_enum = Enum(
    *[s.value for s in IncidentStatus], name="incident_status", create_type=False
)
severity_enum = Enum(*[s.value for s in Severity], name="severity", create_type=False)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        incident_status_enum, default=IncidentStatus.DETECTED.value, nullable=False
    )
    severity: Mapped[str | None] = mapped_column(severity_enum)
    severity_confidence: Mapped[float | None] = mapped_column()
    primary_service_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id")
    )
    affected_service_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    suspected_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("deployments.id")
    )
    repo_full_name: Mapped[str | None] = mapped_column(String)
    base_ref: Mapped[str | None] = mapped_column(String)

    detected_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column()
    triaged_at: Mapped[datetime | None] = mapped_column()
    diagnosed_at: Mapped[datetime | None] = mapped_column()
    approved_at: Mapped[datetime | None] = mapped_column()
    recovered_at: Mapped[datetime | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column()

    root_cause_summary: Mapped[str | None] = mapped_column(Text)
    closed_reason: Mapped[str | None] = mapped_column(Text)
    chain_head_hash: Mapped[bytes | None] = mapped_column()
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
