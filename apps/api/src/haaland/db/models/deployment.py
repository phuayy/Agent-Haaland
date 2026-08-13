from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, default="github", nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    commit_sha: Mapped[str] = mapped_column(String, nullable=False)
    previous_sha: Mapped[str | None] = mapped_column(String)
    ref: Mapped[str | None] = mapped_column(String)
    author_login: Mapped[str | None] = mapped_column(String)
    pr_number: Mapped[int | None] = mapped_column()
    environment: Mapped[str] = mapped_column(String, default="production", nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    changed_files: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    diff_summary: Mapped[dict | None] = mapped_column(JSONB)
    deployed_at: Mapped[datetime] = mapped_column(nullable=False)
