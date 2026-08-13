"""The human gate (docs/05, docs/08 Phase 3's hardest problem). Execution
genuinely stops here — the checkpoint is written to Postgres by LangGraph
before this coroutine suspends, so a worker restart loses nothing. Resume is
triggered from api/routes/approvals.py via
`graph.ainvoke(Command(resume=...), config={"configurable": {"thread_id": incident_id}})`.

No Slack integration in this slice (out of scope, see plan) — the approval
card is the PR itself plus `GET /api/incidents/{id}` for the dashboard-less
API consumer; approving happens via `POST /api/incidents/{id}/approve`."""

from __future__ import annotations

from langgraph.types import interrupt

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, IncidentStatus
from haaland.domain.events import EventType


async def request_approval_node(state, deps) -> dict:
    incident_id = state["incident_id"]

    decision = interrupt(
        {
            "awaiting": "human_approval",
            "incident_reference": state["reference"],
            "remediation_id": state.get("remediation_id"),
            "pr_url": state.get("pr_url"),
        }
    )

    outcome = decision.get("decision", "approve")
    actor = decision.get("actor", "unknown")
    reason = decision.get("reason")

    async with node_context(deps) as ctx:
        if outcome == "approve":
            await ctx.incident_service.transition(
                incident_id,
                IncidentStatus.APPROVED,
                actor_type=ActorType.HUMAN,
                actor_label=actor,
                summary=f"{actor} approved the remediation",
                event_type=EventType.APPROVAL_GRANTED.value,
                payload={"channel": decision.get("channel", "api")},
            )
            approval = "approved"
        elif outcome == "reject":
            await ctx.incident_service.transition(
                incident_id,
                IncidentStatus.REJECTED,
                actor_type=ActorType.HUMAN,
                actor_label=actor,
                summary=f"{actor} rejected the remediation: {reason or 'no reason given'}",
                event_type=EventType.APPROVAL_DENIED.value,
                payload={"reason": reason},
            )
            approval = "rejected"
        else:
            await ctx.audit.record(
                incident_id,
                EventType.APPROVAL_ESCALATED.value,
                actor_type=ActorType.SYSTEM,
                actor_label="request_approval",
                summary="Approval escalated",
            )
            approval = "escalated"

    return {"approval": approval, "last_failure_detail": reason}
