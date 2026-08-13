"""No-op TicketProvider. Jira/Linear adapters are out of scope for this
slice (docs Phase 5) — P3/P4 incidents still need somewhere to land, so
this records the ticket intent as a structured no-op rather than the node
silently skipping the step. Swap for JiraProvider/LinearProvider later; the
node that calls this (file_ticket) does not change."""

from __future__ import annotations

import uuid


class NullTicketProvider:
    async def create_ticket(self, *, title: str, description: str, evidence: dict) -> str:
        return f"local-ticket-{uuid.uuid4().hex[:8]}"
