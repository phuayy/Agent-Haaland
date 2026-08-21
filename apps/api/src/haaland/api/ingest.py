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
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.errors import IllegalTransition
from haaland.domain.events import EventType
from haaland.domain.models import DebugSessionRequest, NotificationMessage
from haaland.integrations.scm.github import parse_repo_url
from haaland.logging import get_logger
from haaland.services.audit_service import AuditService
from haaland.services.incident_service import IncidentService

logger = get_logger(__name__)


async def _fail_unenqueued(deps, incident_id, reference: str, exc: Exception) -> None:
    """The incident row exists but no worker will ever pick it up. Nothing
    downstream can notice that — the graph never ran, so no node and no
    crash handler is in play — which makes this the only place the gap
    between "accepted" and "started" can be reported at all."""
    try:
        async with session_scope() as session:
            incidents = IncidentRepository(session)
            audit = AuditService(EventRepository(session))
            await IncidentService(incidents, audit).transition(
                incident_id,
                IncidentStatus.FAILED,
                actor_type=ActorType.SYSTEM,
                actor_label="api",
                summary=f"Could not enqueue the debug session run: {exc}",
                event_type=EventType.RUN_FAILED.value,
                payload={"error_type": type(exc).__name__, "detail": str(exc)},
            )
    except (IllegalTransition, LookupError):
        logger.warning("could not mark unenqueued incident failed", reference=reference, exc_info=True)

    if deps is None:
        return
    try:
        await deps.notifications.broadcast(
            NotificationMessage(
                kind="escalated",
                title=f"[{reference}] Intake failed — run never started",
                body_markdown=(
                    f"**Error:** {type(exc).__name__}: {exc}\n\n"
                    f"The incident was recorded but could not be handed to the worker "
                    f"queue, so no triage will happen. This incident needs a human."
                ),
                incident_reference=reference,
                links={"Incident": f"{deps.settings.app_base_url}/incidents/{reference}"},
            )
        )
    except Exception:  # noqa: BLE001 - the queue failure is what the caller must see
        logger.warning("could not notify on unenqueued incident", reference=reference, exc_info=True)


async def launch_debug_session(
    request: DebugSessionRequest, arq_pool: ArqRedis, *, deps=None
) -> tuple[str, str]:
    """Persist an incident, enqueue the graph run, return (reference, incident_id).

    Raises ValueError if repo_url is not a parseable GitHub repository URL —
    callers map that onto their own status code.

    `deps` is optional only so a caller that has no container to hand (tests,
    scripts) still works; without it a failed enqueue is still marked FAILED,
    it just isn't announced on any channel.
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

    try:
        await arq_pool.enqueue_job("run_debug_session", str(incident_id), initial_state)
    except Exception as exc:
        # A Redis outage here is silent by construction: the caller gets a 5xx
        # it may or may not retry, and the incident sits at DETECTED forever.
        logger.exception("could not enqueue debug session", reference=reference)
        await _fail_unenqueued(deps, incident_id, reference, exc)
        raise

    return reference, str(incident_id)
