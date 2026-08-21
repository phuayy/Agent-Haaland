"""Stage 1's deterministic half, run before the model ever reasons about the
bug — see services/code_search_service.py. Also collects deployment context
(recent commits on base_ref, straight off the clone) into the evidence
bundle: for an alert-shaped incident with no traceback it is often the
single strongest signal available.

This node is additionally the only writer of `trace` evidence: the failure
path (frames, call chain, terminating error signature) is parsed here for
the diagnosis prompt anyway, so it is persisted in the same pass rather than
being recomputed later from a log the system no longer keeps.
"""

from __future__ import annotations

from haaland.agent.nodes._context import node_context, workspace_from_state
from haaland.domain.enums import ActorType, EvidenceKind
from haaland.domain.events import EventType
from haaland.domain.models import FailureTrace
from haaland.llm.rendering import format_recent_commits
from haaland.services.code_search_service import build_failure_trace

_DEPLOY_CONTEXT_HOURS = 24
_TRACE_RELEVANCE = 0.9


def _trace_content(trace: FailureTrace, exception_message: str | None) -> dict:
    """The `trace` evidence row's JSONB payload. `exception_message` is
    passed in already redacted rather than read off `trace` — see the call
    site."""
    return {
        "call_chain": trace.call_chain,
        "frames": [frame.model_dump() for frame in trace.frames],
        "exception_class": trace.exception_class,
        "exception_message": exception_message,
    }


async def locate_code_node(state, deps) -> dict:
    incident_id = state["incident_id"]
    workspace = await workspace_from_state(deps, state)

    candidates = deps.code_search.locate(workspace, state["log_text"])
    trace = build_failure_trace(state["log_text"])

    # Deploy context is gathered after the redact node ran, so it passes
    # through the redaction choke point itself before entering the bundle —
    # commit messages and author names are as untrusted as log lines.
    commits = workspace.recent_commits(hours=_DEPLOY_CONTEXT_HOURS)
    deploy_context: list[dict] = []
    if commits:
        redacted = await deps.redactor.redact_text(incident_id, format_recent_commits(commits))
        deploy_context = [{"rendered": redacted.text}]

    # The exception message is the one part of the trace that is rendered
    # runtime data — an account number, an email, a quoted user value can all
    # end up in it — so it goes through the same choke point before being
    # persisted. Frame paths and function names are source identifiers and
    # are already stored verbatim as `source_ref` on the candidate rows.
    exception_message: str | None = None
    if trace.exception_message:
        redacted_message = await deps.redactor.redact_text(incident_id, trace.exception_message)
        exception_message = redacted_message.text

    bundle = state["evidence"].model_copy(
        update={
            "code_candidates": candidates,
            "call_chain": trace.call_chain,
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
        # Written only when the log actually yielded a path or an error
        # signature: an empty trace row would be indistinguishable from a
        # parsed-but-empty one downstream, and the absence of the row is what
        # tells the dashboard it has no real path to draw.
        if trace.frames or trace.exception_class:
            raise_site = trace.raise_site
            await ctx.evidence.add(
                incident_id=incident_id,
                kind=EvidenceKind.TRACE,
                source="traceback",
                source_ref=f"{raise_site.path}:{raise_site.line}" if raise_site else None,
                content=_trace_content(trace, exception_message),
                relevance=_TRACE_RELEVANCE,
            )
        summary = f"Located {len(candidates)} candidate location(s)"
        if not candidates:
            # Never silently proceed on zero candidates: name the situation
            # so the post-mortem reads "cold start", not "the model failed".
            summary += (
                " — no traceback frame or error literal matched; "
                "diagnosis runs in cold-start exploration mode"
            )
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
