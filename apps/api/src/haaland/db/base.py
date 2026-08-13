from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # Every migration column is `timestamptz` (see migrations/versions/
    # 0001_core_schema.py) but SQLAlchemy's default inference from a bare
    # `datetime` type annotation is a naive TIMESTAMP WITHOUT TIME ZONE.
    # Without this override every `Mapped[datetime]` column mismatches its
    # actual Postgres type and asyncpg rejects the first write with a
    # "can't subtract offset-naive and offset-aware datetimes" error.
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }
