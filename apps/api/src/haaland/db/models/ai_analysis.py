from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base
from haaland.db.models.incident import Incident  # noqa: F401 — FK target import ordering


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    stage: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    prompt_hash: Mapped[bytes] = mapped_column(nullable=False)
    redaction_map_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String)
    input_tokens: Mapped[int | None] = mapped_column()
    output_tokens: Mapped[int | None] = mapped_column()
    cache_read_tokens: Mapped[int | None] = mapped_column()
    cache_write_tokens: Mapped[int | None] = mapped_column()
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
