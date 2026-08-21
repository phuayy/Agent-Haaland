"""Stage 1's deterministic half, run before the model ever reasons about the
bug — see services/code_search_service.py. Also collects deployment context
(recent commits on base_ref, straight off the clone) into the evidence
bundle: for an alert-shaped incident with no traceback it is often the
single strongest signal available."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context, workspace_from_state
from haaland.domain.enums import ActorType, EvidenceKind
from haaland.domain.events import EventType
from haaland.llm.rendering import format_recent_commits
from haaland.services.code_search_service import extract_call_chain

_DEPLOY_CONTEXT_HOURS = 24


async def locate_code_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = await workspace_from_state(deps, state)

    candidates = deps.code_search.locate(workspace, state["log_text"])
    call_chain = extract_call_chain(state["log_text"])

    # Deploy context is gathered after the redact node ran, so it passes
    # through the redaction choke point itself before entering the bundle —
    # commit messages and author names are as untrusted as log lines.
    commits = workspace.recent_commits(hours=_DEPLOY_CONTEXT_HOURS)
    deploy_context: list[dict] = []
    if commits:
        redacted = await deps.redactor.redact_text(incident_id, format_recent_commits(commits))
        deploy_context = [{"rendered": redacted.text}]

    bundle = state["evidence"].model_copy(
        update={
            "code_candidates": candidates,
            "call_chain": call_chain,
            "deploy_context": deploy_context,
        }
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
        if commits:
            await ctx.evidence.add(
                incident_id=incident_id,
                kind=EvidenceKind.SOURCE,
                source="workspace",
                source_ref=f"git log --since={_DEPLOY_CONTEXT_HOURS}h",
                content={"commit_count": len(commits)},
                relevance=0.5,
            )
        summary = f"Located {len(candidates)} candidate location(s)"
        if not candidates:
            # Never silently proceed on zero candidates: name the situation
            # so the post-mortem reads "cold start", not "the model failed".
            summary += " — no traceback frame or error literal matched; diagnosis runs in cold-start exploration mode"
        await ctx.audit.record(
            incident_id,
            EventType.CODE_LOCATED.value,
            actor_type=ActorType.SYSTEM,
            actor_label="locate_code",
            summary=summary,
            payload={
                "candidates": [f"{c.path}:{c.start_line}-{c.end_line}" for c in candidates],
                "cold_start": not candidates,
                "deploy_context_commits": len(commits),
            },
        )

    return {"evidence": bundle}
