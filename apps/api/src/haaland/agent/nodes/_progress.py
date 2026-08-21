"""Delivery half of the progress pings; services/progress_service.py holds
the wording and the rules about how many there are.

Everything here is best-effort and silent on failure. A progress card is
the least important thing this pipeline does — it exists so a human is not
staring at an empty chat — and it runs inside nodes whose actual job is to
diagnose and patch a production incident. A Lark outage, a revoked token,
or a bug in this module must cost the run a log line and nothing else.

Hence the catch-all: NotificationService already absorbs a channel raising
NotificationError, but not an adapter raising anything else, and not the
delivery-row write below. And hence the separate `node_context`: the ping
is recorded in its own session so a failure writing a heartbeat can never
poison the transaction the calling node is using for the work that
matters."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import Severity
from haaland.logging import get_logger
from haaland.services.progress_service import ProgressStage, progress_message

logger = get_logger(__name__)


async def announce_progress(
    state,
    deps,
    stage: ProgressStage,
    *,
    severity: Severity | None = None,
    detail: str | None = None,
) -> None:
    """Post one milestone card on every configured channel and record what
    was delivered. Never raises."""
    if not deps.settings.notify_progress:
        return

    try:
        message = progress_message(
            stage,
            reference=state["reference"],
            service_name=state["service_name"],
            severity=severity,
            detail=detail,
        )
        deliveries = await deps.notifications.broadcast(message)
        async with node_context(deps) as ctx:
            for delivery in deliveries:
                await ctx.notifications.record(
                    incident_id=state["incident_id"],
                    channel=delivery.channel,
                    target=delivery.channel,
                    status=delivery.status,
                    external_ref=delivery.external_ref,
                    payload={"kind": message.kind, "stage": stage, "detail": delivery.detail},
                )
    except Exception:  # noqa: BLE001 - a heartbeat must never fail an incident
        logger.warning(
            "progress notification failed",
            stage=stage,
            reference=state.get("reference"),
            exc_info=True,
        )
