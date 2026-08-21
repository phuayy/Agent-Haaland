"""Link incidents created before the service registry existed.

`incidents.primary_service_id` has been a column since migration 0001 but
nothing set it until the registry endpoints landed, so every incident opened
before then is unattached — and an unattached incident is invisible to
`GET /api/services`: its service card shows no history and stays green while
the incident is still open.

The service name is recoverable from the title, which ingest writes as
"Debug session — {service_name}". Incidents whose title does not match that
shape are left alone and reported.

    python scripts/backfill_incident_services.py --dry-run
    python scripts/backfill_incident_services.py

Idempotent: already-linked incidents are skipped, and a service that does not
exist yet is created with the incident's repository.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from haaland.config import get_settings
from haaland.db.models.incident import Incident
from haaland.db.repositories.services import ServiceRepository
from haaland.db.session import init_engine, session_scope

TITLE_PREFIX = "Debug session — "

# The placeholder in demo/seed_repo/sample_request.json. Recording it on a
# service would put a dead link on the card.
PLACEHOLDER_REPOS = {"<you>/<repo>"}


def _service_name(title: str) -> str | None:
    if not title.startswith(TITLE_PREFIX):
        return None
    name = title.removeprefix(TITLE_PREFIX).strip()
    return name or None


async def main(dry_run: bool) -> None:
    init_engine(get_settings())
    linked, skipped = 0, []
    async with session_scope() as session:
        services = ServiceRepository(session)
        rows = (
            await session.scalars(
                select(Incident)
                .where(Incident.primary_service_id.is_(None))
                .order_by(Incident.detected_at)
            )
        ).all()

        for incident in rows:
            name = _service_name(incident.title)
            if name is None:
                skipped.append(f"{incident.reference}: title does not name a service")
                continue
            if dry_run:
                print(f"  would link {incident.reference} -> {name}")
                linked += 1
                continue
            repo = incident.repo_full_name
            service = await services.get_or_create_by_name(
                name=name,
                repo_full_name=None if repo in PLACEHOLDER_REPOS else repo,
                base_ref=incident.base_ref or "main",
            )
            incident.primary_service_id = service.id
            print(f"  linked {incident.reference} -> {name}")
            linked += 1

        if dry_run:
            await session.rollback()

    print(f"{'would link' if dry_run else 'linked'}: {linked}, skipped: {len(skipped)}")
    for line in skipped:
        print(f"  skipped {line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
