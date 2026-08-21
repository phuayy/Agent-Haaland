"""Stage 5. PR body always carries the automated-content banner and the AI
root cause regardless of what the model wrote (docs/04's pr_body.md.j2
contract) — the model's prose is embedded inside a fixed wrapper, not
trusted to include the banner itself. Reviewers come from CODEOWNERS,
deterministically, not from the model."""

from __future__ import annotations

import uuid

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.events import EventType
from haaland.domain.models import NotificationMessage
from haaland.integrations.scm.github import parse_repo_url


async def open_pr_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    remediation = state["remediation"]
    diagnosis = state["diagnosis"]
    ref = parse_repo_url(state["repo_url"])

    codeowners_text = await deps.scm.get_codeowners(ref, state["branch_name"])
    reviewers = deps.codeowners.reviewers_for(codeowners_text, state["changed_paths"])

    body = deps.postmortem.render_pr_body(
        incident_reference=state["reference"],
        dashboard_url=deps.settings.incident_url(state["reference"]),
        root_cause=diagnosis.root_cause,
        confidence=diagnosis.confidence,
        body_markdown=remediation.pr_body_markdown,
    )

    pr = await deps.scm.open_pull_request(
        ref,
        branch_name=state["branch_name"],
        base_branch=state["base_ref"],
        title=remediation.pr_title,
        body=body,
        labels=["incident", "automated", "needs-review"],
        reviewers=reviewers,
    )

    # Inform code owners / team lead on the configured channels (Lark
    # today). Delivery results are recorded per channel; a channel being
    # down never blocks the approval gate.
    dashboard_url = deps.settings.incident_url(state["reference"])
    classification = state.get("classification")
    message = NotificationMessage(
        kind="approval_requested",
        title=f"[{state['reference']}] Fix drafted — review required",
        body_markdown=(
            f"**Service:** {state['service_name']}\n"
            f"**Root cause:** {diagnosis.root_cause}\n\n"
            f"A remediation PR has been drafted and verified by static checks. "
            f"The agent cannot merge it — a human review is required."
        ),
        incident_reference=state["reference"],
        severity=classification.severity if classification else None,
        links={"Review PR": pr.url, "Incident": dashboard_url},
        mentions=reviewers,
    )
    deliveries = await deps.notifications.broadcast(message)

    async with node_context(deps) as ctx:
        if state.get("remediation_id"):
            await ctx.remediations.set_pr(
                uuid.UUID(state["remediation_id"]), pr_number=pr.number, pr_url=pr.url
            )
        await ctx.audit.record(
            incident_id,
            EventType.PR_OPENED.value,
            actor_type=ActorType.SYSTEM,
            actor_label="open_pr",
            summary=f"Opened PR #{pr.number}: {remediation.pr_title}",
            payload={"pr_number": pr.number, "pr_url": pr.url, "reviewers": reviewers},
        )
        for delivery in deliveries:
            await ctx.notifications.record(
                incident_id=incident_id,
                channel=delivery.channel,
                target=delivery.channel,  # webhook bots have no addressable target beyond the channel
                status=delivery.status,
                external_ref=delivery.external_ref,
                payload={"kind": message.kind, "detail": delivery.detail},
            )
            await ctx.audit.record(
                incident_id,
                EventType.NOTIFICATION_SENT.value,
                actor_type=ActorType.INTEGRATION,
                actor_label=delivery.channel,
                summary=f"Notification {delivery.status} via {delivery.channel}"
                + (f": {delivery.detail}" if delivery.detail else ""),
                payload={"status": delivery.status, "external_ref": delivery.external_ref},
            )
        await ctx.incident_service.transition(
            incident_id,
            IncidentStatus.AWAITING_APPROVAL,
            actor_type=ActorType.SYSTEM,
            actor_label="open_pr",
            summary=f"Awaiting human approval — PR #{pr.number} open, not mergeable by the agent",
            event_type=EventType.APPROVAL_REQUESTED.value,
            payload={"pr_url": pr.url},
        )

    return {"pr_number": pr.number, "pr_url": pr.url}
