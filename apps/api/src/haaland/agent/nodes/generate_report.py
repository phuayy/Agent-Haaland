"""Stage 6. Assembled, not written — the timeline table is rendered
directly from `incident_events`; the model supplies prose only
(docs/05, docs/00's "documentation is generated continuously, not
reconstructed after it").

This slice does not watch a live deploy or poll for recovery (that needs
the observability plane, out of scope) — the remediating/verifying/
documenting transitions are recorded as pass-through with an explicit note,
so the state machine and the report are both honest about what was and
wasn't actually verified."""

from __future__ import annotations

import uuid

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.errors import AIRefusalError
from haaland.domain.events import EventType
from haaland.domain.models import NotificationMessage, PostmortemProse
from haaland.llm.rendering import render_report_input


async def generate_report_node(state, deps) -> dict:
    incident_id = state["incident_id"]

    async with node_context(deps) as ctx:
        incident = await ctx.incidents.get(incident_id)
        assert incident is not None

        pass_through_steps = (
            (IncidentStatus.REMEDIATING, EventType.PR_MERGED, "Human merge assumed — not polled"),
            (
                IncidentStatus.VERIFYING,
                EventType.DEPLOY_COMPLETED,
                "Deploy status not polled in this slice",
            ),
            (
                IncidentStatus.DOCUMENTING,
                EventType.METRICS_RECOVERED,
                "Recovery not verified — no live metrics source wired",
            ),
        )
        if incident.status == IncidentStatus.APPROVED.value:
            for target, event_type, note in pass_through_steps:
                await ctx.incident_service.transition(
                    incident_id, target,
                    actor_type=ActorType.SYSTEM, actor_label="generate_report",
                    summary=note, event_type=event_type.value,
                )
            incident = await ctx.incidents.get(incident_id)
            if state.get("remediation_id"):
                await ctx.remediations.resolve(uuid.UUID(state["remediation_id"]), "merged")

        events = await ctx.audit.timeline(incident_id)
        chain = await ctx.audit.verify(incident_id)

        incident_summary = {
            "reference": incident.reference,
            "title": incident.title,
            "severity": incident.severity,
            "root_cause_summary": incident.root_cause_summary,
            "repo_full_name": incident.repo_full_name,
        }
        event_dicts = [
            {"seq": e.seq, "event_type": e.event_type, "actor_label": e.actor_label, "summary": e.summary}
            for e in events
        ]

        try:
            prose = await ctx.llm_call.call(
                incident_id=incident_id,
                stage="report",
                redacted_text=render_report_input(incident_summary, event_dicts),
                output_schema=PostmortemProse,
            )
        except AIRefusalError:
            prose = PostmortemProse(
                summary="Report generation was refused by the model.",
                root_cause_narrative=incident.root_cause_summary or "n/a",
                resolution_narrative="n/a",
                went_well="n/a",
                went_wrong="Post-mortem prose generation failed.",
                action_items=["Regenerate this report."],
            )

        markdown = deps.postmortem.render(
            incident=incident, events=events, prose=prose, chain_verified=chain["valid"]
        )

        from haaland.db.models.postmortem import Postmortem

        ctx.session.add(Postmortem(incident_id=incident_id, markdown=markdown))

        current_status = IncidentStatus(incident.status)
        if current_status != IncidentStatus.CLOSED:
            await ctx.incident_service.transition(
                incident_id,
                IncidentStatus.CLOSED,
                actor_type=ActorType.SYSTEM,
                actor_label="generate_report",
                summary="Post-mortem generated; incident closed; chain sealed",
                event_type=EventType.POSTMORTEM_GENERATED.value,
                payload={"chain_valid": chain["valid"]},
            )

        closing_message = NotificationMessage(
            kind="incident_closed",
            title=f"[{incident.reference}] Incident closed — post-mortem ready",
            body_markdown=(
                f"**Root cause:** {incident.root_cause_summary or 'n/a'}\n"
                f"**Audit chain:** {'verified' if chain['valid'] else 'BROKEN — investigate'}"
            ),
            incident_reference=incident.reference,
            links={
                "Post-mortem": f"{deps.settings.app_base_url}/api/incidents/{incident.reference}/postmortem",
                **({"PR": state["pr_url"]} if state.get("pr_url") else {}),
            },
        )
        for delivery in await deps.notifications.broadcast(closing_message):
            await ctx.notifications.record(
                incident_id=incident_id,
                channel=delivery.channel,
                target=delivery.channel,
                status=delivery.status,
                external_ref=delivery.external_ref,
                payload={"kind": closing_message.kind, "detail": delivery.detail},
            )

    # Terminal node for every path that cloned a workspace (approved and
    # escalated alike) — delete the disposable clone or it outlives the
    # incident on the instance's disk.
    deps.workspace.cleanup(incident_id, state.get("workspace_path"))

    return {}
