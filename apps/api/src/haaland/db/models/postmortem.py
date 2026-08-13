from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base


class Postmortem(Base):
    __tablename__ = "postmortems"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_ref: Mapped[str | None] = mapped_column(String)
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column()
