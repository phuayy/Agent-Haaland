"""The compliance artefact. Everything else in the schema is an optimisation
over this table. Append-only-ness is enforced by a DB trigger — see
migrations/versions/0001_core_schema.py — not by application discipline."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base
from haaland.domain.enums import ActorType

actor_type_enum = Enum(*[a.value for a in ActorType], name="actor_type", create_type=False)


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    __table_args__ = (UniqueConstraint("incident_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[str] = mapped_column(actor_type_enum, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String)
    actor_label: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    prev_hash: Mapped[bytes | None] = mapped_column()
    hash: Mapped[bytes] = mapped_column(nullable=False)
