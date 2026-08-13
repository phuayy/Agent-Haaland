from __future__ import annotations

import base64
import secrets

import pytest

from haaland.redaction.service import Redactor
from haaland.redaction.vault import TokenVault


class FakeRedis:
    """The two calls TokenVault makes — `set` and `get` — backed by an
    in-process dict. Real Redis is exercised separately in integration
    tests; unit tests for the redaction boundary shouldn't need a live
    server to run in a few milliseconds."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def vault(fake_redis: FakeRedis) -> TokenVault:
    key = base64.b64encode(secrets.token_bytes(32)).decode()
    return TokenVault(fake_redis, key, ttl_hours=24)


@pytest.fixture
def redactor(vault: TokenVault) -> Redactor:
    return Redactor(vault)
