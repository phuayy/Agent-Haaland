"""AES-GCM token vault in Redis. 24h TTL. The LLM never receives this; only
authenticated humans rehydrate, and rehydration is itself an audited read
(docs/02, docs/09)."""

from __future__ import annotations

import base64
import json
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.asyncio import Redis

from haaland.domain.errors import RedactionUnavailable


class TokenVault:
    def __init__(self, redis: Redis, encryption_key_b64: str, ttl_hours: int = 24) -> None:
        self._redis = redis
        self._aead = AESGCM(base64.b64decode(encryption_key_b64))
        self._ttl_seconds = ttl_hours * 3600

    def _key(self, incident_id: uuid.UUID) -> str:
        return f"vault:{incident_id}"

    async def write(self, incident_id: uuid.UUID, mapping: dict[str, str]) -> str:
        nonce = os.urandom(12)
        plaintext = json.dumps(mapping).encode("utf-8")
        ciphertext = self._aead.encrypt(nonce, plaintext, associated_data=str(incident_id).encode())
        blob = base64.b64encode(nonce + ciphertext).decode("ascii")
        key = self._key(incident_id)
        try:
            await self._redis.set(key, blob, ex=self._ttl_seconds)
        except Exception as exc:  # Redis unavailable — fail closed on redaction (docs/09)
            raise RedactionUnavailable(str(exc)) from exc
        return key

    async def read(self, incident_id: uuid.UUID) -> dict[str, str] | None:
        key = self._key(incident_id)
        blob = await self._redis.get(key)
        if blob is None:
            return None
        raw = base64.b64decode(blob)
        nonce, ciphertext = raw[:12], raw[12:]
        plaintext = self._aead.decrypt(nonce, ciphertext, associated_data=str(incident_id).encode())
        return json.loads(plaintext)

    async def rehydrate_value(self, incident_id: uuid.UUID, token: str) -> str | None:
        mapping = await self.read(incident_id)
        return mapping.get(token) if mapping else None
