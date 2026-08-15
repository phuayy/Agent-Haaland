"""incident reference sequence.

The previous reference scheme counted existing rows (`SELECT count(*)`),
which races: two concurrent debug sessions could both count N and both try
to insert INC-YYYY-{N+1}, and the second would die on the unique
constraint. A Postgres sequence is atomic under concurrency by
construction. References become globally monotonic rather than resetting
each year — an acceptable trade for correctness, and arguably better for
humans quoting them.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS incident_reference_seq START 1")
    # Start above anything already issued by the old count-based scheme.
    op.execute(
        """
        SELECT setval(
          'incident_reference_seq',
          GREATEST(
            (SELECT COALESCE(MAX(split_part(reference, '-', 3)::int), 0) FROM incidents
             WHERE reference ~ '^INC-\\d{4}-\\d+$'),
            1
          )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS incident_reference_seq")
