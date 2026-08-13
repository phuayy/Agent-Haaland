"""Stage 0. Nothing downstream of this node may see unredacted evidence —
every later node reads state["evidence"], which from this point on is
always the redacted bundle (docs/05)."""

from __future__ import annotations

from haaland.agent.nodes._context import node_context
from haaland.agent.state import IncidentState
from haaland.domain.enums import ActorType
from haaland.domain.events import EventType


async def redact_node(state: IncidentState, deps) -> dict:
    incident_id = state["incident_id"]
    bundle = state["evidence"]
    assert bundle is not None

    redacted_bundle, result = await deps.redactor.redact_bundle(incident_id, bundle)

    async with node_context(deps) as ctx:
        await ctx.redaction_maps.record(
            incident_id=incident_id,
            vault_key=result.vault_key,
            entity_counts=result.entity_counts,
            ttl_hours=deps.settings.vault_ttl_hours,
        )
        await ctx.audit.record(
            incident_id,
            EventType.PII_REDACTED.value,
            actor_type=ActorType.SYSTEM,
            actor_label="redact",
            summary=f"Redacted evidence: {sum(result.entity_counts.values())} entities across "
            f"{len(result.entity_counts)} type(s)",
            payload={"entity_counts": result.entity_counts},
        )

    return {"evidence": redacted_bundle, "redaction": result}
