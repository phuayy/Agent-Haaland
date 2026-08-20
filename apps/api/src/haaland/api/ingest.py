"""The one place a debug session is created and enqueued.

Both entrypoints funnel through here: the first-party
`POST /api/debug-sessions` and the `POST /webhooks/alertmanager` webhook.
Keeping it in the api layer (not services/) is deliberate — it touches the
arq pool, and the import-linter contract "services stay framework-free"
forbids `arq` there.
"""

from __future__ import annotations

from arq import ArqRedis

from haaland.db.repositories.events import EventRepository
from haaland.db.repositories.incidents import IncidentRepository
from haaland.db.session import session_scope
from haaland.domain.models import DebugSessionRequest
from haaland.integrations.scm.github import parse_repo_url
from haaland.services.audit_service import AuditService
from haaland.services.incident_service import IncidentService


async def launch_debug_session(
    request: DebugSessionRequest, arq_pool: ArqRedis
) -> tuple[str, str]:
    """Persist an incident, enqueue the graph run, return (reference, incident_id).

    Raises ValueError if repo_url is not a parseable GitHub repository URL —
    callers map that onto their own status code.
    """
    ref = parse_repo_url(request.repo_url)

    async with session_scope() as session:
        audit = AuditService(EventRepository(session))
        incidents = IncidentRepository(session)
        incident_service = IncidentService(incidents, audit)
        incident = await incident_service.open_from_debug_session(
            service_name=request.service_name,
            repo_full_name=ref.full_name,
            base_ref=request.base_ref,
        )
        incident_id = incident.id
        reference = incident.reference

    initial_state = {
        "incident_id": incident_id,
        "reference": reference,
        "service_name": request.service_name,
        "repo_url": request.repo_url,
        "repo_full_name": ref.full_name,
        "base_ref": request.base_ref,
        "log_text": request.log_text,
        "fix_attempt": 0,
        "check_reports": [],
        "errors": [],
        "cost_usd": 0.0,
    }

    await arq_pool.enqueue_job("run_debug_session", str(incident_id), initial_state)

    return reference, str(incident_id)
