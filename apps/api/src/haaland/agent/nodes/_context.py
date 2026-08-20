"""Every node opens exactly one of these per invocation — a session-scoped
bundle of the repository-backed services. Kept out of deps.py because a
DB session must not outlive a single unit of work (docs/07 layering:
db/session.py owns session lifetime, not the process-wide container)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.repositories.ai_analyses import AIAnalysisRepository
from haaland.db.repositories.events import EventRepository
from haaland.db.repositories.evidence import EvidenceRepository
from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.repositories.notifications import NotificationRepository
from haaland.db.repositories.redaction_maps import RedactionMapRepository
from haaland.db.repositories.remediations import RemediationRepository
from haaland.db.session import session_scope
from haaland.llm.tools import supports_tool_loop
from haaland.services.audit_service import AuditService
from haaland.services.incident_service import IncidentService
from haaland.services.llm_call_service import LLMCallService
from haaland.services.tool_loop_service import ToolLoopService


@dataclass
class NodeContext:
    session: AsyncSession
    incidents: IncidentRepository
    evidence: EvidenceRepository
    remediations: RemediationRepository
    redaction_maps: RedactionMapRepository
    notifications: NotificationRepository
    audit: AuditService
    incident_service: IncidentService
    llm_call: LLMCallService
    # None when the configured provider isn't tool-capable (fake, openai) —
    # nodes fall back to the single-shot llm_call path.
    tool_loop: ToolLoopService | None


@asynccontextmanager
async def node_context(deps) -> AsyncIterator[NodeContext]:
    async with session_scope() as session:
        events_repo = EventRepository(session)
        audit = AuditService(events_repo)
        incidents_repo = IncidentRepository(session)
        analyses_repo = AIAnalysisRepository(session)
        tool_loop = (
            ToolLoopService(
                deps.llm,
                analyses_repo,
                deps.budget,
                deps.redactor,
                max_iterations=deps.settings.tool_loop_max_iterations,
            )
            if supports_tool_loop(deps.llm)
            else None
        )
        yield NodeContext(
            session=session,
            incidents=incidents_repo,
            evidence=EvidenceRepository(session),
            remediations=RemediationRepository(session),
            redaction_maps=RedactionMapRepository(session),
            notifications=NotificationRepository(session),
            audit=audit,
            incident_service=IncidentService(incidents_repo, audit),
            llm_call=LLMCallService(deps.llm, analyses_repo, deps.budget),
            tool_loop=tool_loop,
        )
