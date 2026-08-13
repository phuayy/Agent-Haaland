from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String)
    window_start: Mapped[datetime | None] = mapped_column()
    window_end: Mapped[datetime | None] = mapped_column()
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_raw_ref: Mapped[str | None] = mapped_column(String)
    relevance: Mapped[float | None] = mapped_column()
    collected_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
