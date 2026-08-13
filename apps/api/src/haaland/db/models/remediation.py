from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from haaland.db.base import Base


class Remediation(Base):
    __tablename__ = "remediations"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    risk_notes: Mapped[str | None] = mapped_column(Text)
    repo_full_name: Mapped[str] = mapped_column(String, nullable=False)
    branch_name: Mapped[str] = mapped_column(String, nullable=False)
    base_sha: Mapped[str] = mapped_column(String, nullable=False)
    patch: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=1, nullable=False)
    pr_number: Mapped[int | None] = mapped_column()
    pr_url: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column()


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    remediation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("remediations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    actor_label: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
