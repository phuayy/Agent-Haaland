from __future__ import annotations

import re
from datetime import UTC, datetime

from haaland.agent.nodes._context import node_context
from haaland.agent.state import IncidentState
from haaland.domain.enums import ActorType, EvidenceKind, IncidentStatus
from haaland.domain.events import EventType
from haaland.domain.models import EvidenceBundle, LogLine

_LEVEL = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b")


def _parse_log_lines(log_text: str) -> list[LogLine]:
    now = datetime.now(UTC)
    lines = []
    for raw in log_text.splitlines():
        if not raw.strip():
            continue
        level_match = _LEVEL.search(raw)
        lines.append(
            LogLine(
                timestamp=now,  # best-effort: parsing arbitrary log timestamp formats is out of scope
                level=level_match.group(1) if level_match else "INFO",
                message=raw,
            )
        )
    return lines


async def ingest_input_node(state: IncidentState, deps) -> dict:
    async with node_context(deps) as ctx:
        log_lines = _parse_log_lines(state["log_text"])
        bundle = EvidenceBundle(
            incident_id=state["incident_id"],
            service_name=state["service_name"],
            repo_full_name=state["repo_full_name"],
            base_ref=state["base_ref"],
            log_lines=log_lines,
        )

        await ctx.evidence.add(
            incident_id=state["incident_id"],
            kind=EvidenceKind.LOG,
            source="user_upload",
            content={"line_count": len(log_lines)},
            relevance=1.0,
        )
        await ctx.incident_service.transition(
            state["incident_id"],
            IncidentStatus.ENRICHING,
            actor_type=ActorType.SYSTEM,
            actor_label="ingest_input",
            summary=f"Ingested {len(log_lines)} log line(s) for {state['service_name']}",
            event_type=EventType.EVIDENCE_COLLECTED.value,
            payload={"line_count": len(log_lines)},
        )

    return {"evidence": bundle}
