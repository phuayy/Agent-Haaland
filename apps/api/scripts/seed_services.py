"""Seed the service registry so a fresh database has something to show.

The dashboard reads `GET /api/services` (there is no hardcoded list in the
frontend any more), which means a freshly migrated database renders an empty
registry. This puts a handful of plausible services in the table for demos
and local development. It is idempotent — a name that already exists is left
untouched, so re-running it after real services were added is safe.

    python scripts/seed_services.py            # inside the api container
    make seed                                  # migrate + seed, from the repo root

Nothing here creates incidents: health pills stay green until a real debug
session runs against one of these services.
"""

from __future__ import annotations

import asyncio

from haaland.config import get_settings
from haaland.db.repositories.services import ServiceRepository
from haaland.db.session import init_engine, session_scope

SEED = [
    {
        "name": "orders-api",
        "repo_url": "https://github.com/haaland-demo/orders-api",
        "tier": 1,
        "owner_team": "Team Orders",
        "base_ref": "main",
    },
    {
        "name": "payments-service",
        "repo_url": "https://github.com/haaland-demo/payments-service",
        "tier": 1,
        "owner_team": "Team Payments",
        "base_ref": "main",
    },
    {
        "name": "auth-service",
        "repo_url": "https://github.com/haaland-demo/auth-service",
        "tier": 2,
        "owner_team": "Team Identity",
        "base_ref": "main",
    },
    {
        "name": "notification-worker",
        "repo_url": "https://github.com/haaland-demo/notification-worker",
        "tier": 3,
        "owner_team": "Team Platform",
        "base_ref": "main",
    },
]


async def main() -> None:
    init_engine(get_settings())
    created, skipped = 0, 0
    async with session_scope() as session:
        repo = ServiceRepository(session)
        for entry in SEED:
            if await repo.get_by_name(entry["name"]) is not None:
                skipped += 1
                continue
            repo_url = str(entry["repo_url"])
            await repo.create(
                name=str(entry["name"]),
                repo_full_name=repo_url.removeprefix("https://github.com/"),
                tier=int(entry["tier"]),
                owner_team=str(entry["owner_team"]),
                base_ref=str(entry["base_ref"]),
                repo_url=repo_url,
            )
            created += 1
    print(f"services seeded: {created} created, {skipped} already present")


if __name__ == "__main__":
    asyncio.run(main())
