"""Owns the hash chain. `append()` is the only way an incident_events row is
ever created — this is the module that makes the compliance claim true.

Canonicalisation is the part people get wrong (docs/03): json.dumps is not
deterministic across insertion orders, so payload bytes are produced with
RFC 8785 JCS (sorted keys, no whitespace), not stdlib json.
"""

from __future__ import annotations

import hashlib
import struct
import uuid
from datetime import UTC, datetime

import rfc8785
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haaland.db.models.incident import Incident
from haaland.db.models.incident_event import IncidentEvent
from haaland.domain.enums import ActorType
from haaland.domain.errors import ChainVerificationError

_ZERO_HASH = b"\x00" * 32


def _occurred_at_bytes(dt: datetime) -> bytes:
    dt = dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f").encode("utf-8") + b"Z"


def compute_hash(
    *,
    prev_hash: bytes | None,
    incident_id: uuid.UUID,
    seq: int,
    event_type: str,
    actor_type: str,
    actor_label: str,
    summary: str,
    payload: dict,
    occurred_at: datetime,
) -> bytes:
    h = hashlib.sha256()
    h.update(prev_hash or _ZERO_HASH)
    h.update(incident_id.bytes)
    h.update(struct.pack(">I", seq))
    h.update(event_type.encode("utf-8"))
    h.update(actor_type.encode("utf-8"))
    h.update(actor_label.encode("utf-8"))
    h.update(summary.encode("utf-8"))
    h.update(rfc8785.dumps(payload))
    h.update(_occurred_at_bytes(occurred_at))
    return h.digest()


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        incident_id: uuid.UUID,
        event_type: str,
        actor_type: ActorType,
        actor_label: str,
        summary: str,
        payload: dict | None = None,
        actor_id: str | None = None,
    ) -> IncidentEvent:
        """Insert the next event in sequence. Serialised per incident with a
        row lock on the parent incident: two concurrent appends (e.g. an
        approval webhook landing while the worker writes a node event) would
        otherwise both read the same head, compute the same seq/prev_hash,
        and the loser would fail the unique constraint mid-transaction.
        FOR UPDATE makes the second writer wait and chain onto the first."""
        await self._session.execute(
            select(Incident.id).where(Incident.id == incident_id).with_for_update()
        )
        head = await self._session.scalar(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.seq.desc())
            .limit(1)
        )
        seq = (head.seq + 1) if head else 1
        prev_hash = head.hash if head else None
        occurred_at = datetime.now(UTC)
        payload = payload or {}

        event_hash = compute_hash(
            prev_hash=prev_hash,
            incident_id=incident_id,
            seq=seq,
            event_type=event_type,
            actor_type=actor_type.value,
            actor_label=actor_label,
            summary=summary,
            payload=payload,
            occurred_at=occurred_at,
        )

        row = IncidentEvent(
            incident_id=incident_id,
            seq=seq,
            event_type=event_type,
            actor_type=actor_type.value,
            actor_id=actor_id,
            actor_label=actor_label,
            summary=summary,
            payload=payload,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            hash=event_hash,
        )
        self._session.add(row)
        await self._session.flush()

        await self._session.execute(
            Incident.__table__.update()
            .where(Incident.id == incident_id)
            .values(chain_head_hash=event_hash)
        )
        return row

    async def list_for_incident(self, incident_id: uuid.UUID) -> list[IncidentEvent]:
        result = await self._session.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.seq.asc())
        )
        return list(result)

    async def verify_chain(self, incident_id: uuid.UUID) -> dict:
        """Walk the chain, recompute each hash, return
        {valid, events_checked, first_divergence_seq}."""
        events = await self.list_for_incident(incident_id)
        prev_hash: bytes | None = None
        for event in events:
            expected = compute_hash(
                prev_hash=prev_hash,
                incident_id=incident_id,
                seq=event.seq,
                event_type=event.event_type,
                actor_type=event.actor_type,
                actor_label=event.actor_label,
                summary=event.summary,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
            if expected != event.hash or event.prev_hash != prev_hash:
                return {
                    "valid": False,
                    "events_checked": event.seq,
                    "first_divergence_seq": event.seq,
                }
            prev_hash = event.hash
        return {"valid": True, "events_checked": len(events), "first_divergence_seq": None}

    async def verify_chain_or_raise(self, incident_id: uuid.UUID) -> None:
        result = await self.verify_chain(incident_id)
        if not result["valid"]:
            raise ChainVerificationError(str(incident_id), result["first_divergence_seq"])
