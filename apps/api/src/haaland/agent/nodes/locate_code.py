"""Stage 1's deterministic half, run before the model ever reasons about the
bug — see services/code_search_service.py."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.domain.enums import ActorType, EvidenceKind
from haaland.domain.events import EventType
from haaland.services.code_search_service import extract_call_chain


async def locate_code_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = deps.workspace.reopen(incident_id, state["workspace_path"], state["base_sha"])

    candidates = deps.code_search.locate(workspace, state["log_text"])
    call_chain = extract_call_chain(state["log_text"])
    bundle = state["evidence"].model_copy(
        update={"code_candidates": candidates, "call_chain": call_chain}
    )

    async with node_context(deps) as ctx:
        for c in candidates:
            await ctx.evidence.add(
                incident_id=incident_id,
                kind=EvidenceKind.SOURCE,
                source="workspace",
                source_ref=f"{c.path}:{c.start_line}-{c.end_line}",
                content={"reason": c.reason, "confidence": c.confidence},
                relevance=c.confidence,
            )
        await ctx.audit.record(
            incident_id,
            EventType.CODE_LOCATED.value,
            actor_type=ActorType.SYSTEM,
            actor_label="locate_code",
            summary=f"Located {len(candidates)} candidate location(s)",
            payload={"candidates": [f"{c.path}:{c.start_line}-{c.end_line}" for c in candidates]},
        )

    return {"evidence": bundle}
