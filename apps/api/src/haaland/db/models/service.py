from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    repo_full_name: Mapped[str | None] = mapped_column(String)
    tier: Mapped[int] = mapped_column(SmallInteger, default=2, nullable=False)
    owner_team: Mapped[str | None] = mapped_column(String)
    slack_channel: Mapped[str | None] = mapped_column(String)
    pagerduty_service_id: Mapped[str | None] = mapped_column(String)
    runbook_url: Mapped[str | None] = mapped_column(String)
    slo_p99_ms: Mapped[int | None] = mapped_column()
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ServiceDependency(Base):
    __tablename__ = "service_dependencies"

    upstream_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )
    downstream_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    critical: Mapped[bool] = mapped_column(default=False, nullable=False)
