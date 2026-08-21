"""Every terminal ending pages someone. The happy paths post their card from
inside a node; these are the endings where no node is left alive to do it —
a crashed graph run and an incident that never reached the worker queue."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest

from haaland.api import ingest
from haaland.tasks import debug_session

INCIDENT_ID = "11111111-1111-1111-1111-111111111111"


class RecordingNotifications:
    def __init__(self, *, explode: bool = False) -> None:
        self.sent: list = []
        self._explode = explode

    async def broadcast(self, message):
        if self._explode:
            raise RuntimeError("lark is down and so is the fallback")
        self.sent.append(message)
        return []


class FakeDeps:
    def __init__(self, *, explode: bool = False) -> None:
        self.notifications = RecordingNotifications(explode=explode)
        self.settings = type("S", (), {"app_base_url": "https://haaland.test"})()


@pytest.fixture
def no_db(monkeypatch):
    """The notification path opens a session only to record delivery rows;
    these tests are about what gets sent, not what gets written."""

    @asynccontextmanager
    async def fake_context(deps):
        yield type("Ctx", (), {"notifications": type("N", (), {"record": _noop})()})()

    async def _noop(**kwargs):
        return None

    monkeypatch.setattr(debug_session, "node_context", fake_context)


async def test_crashed_run_pages_with_the_status_it_died_at(no_db):
    deps = FakeDeps()

    await debug_session._notify_crash(
        deps, INCIDENT_ID, "INC-2026-0001", "diagnosing", RuntimeError("provider timeout")
    )

    (message,) = deps.notifications.sent
    assert message.kind == "escalated"
    assert message.incident_reference == "INC-2026-0001"
    assert "diagnosing" in message.body_markdown
    assert "RuntimeError: provider timeout" in message.body_markdown


async def test_notification_failure_never_masks_the_crash(no_db):
    """_mark_failed runs on the way out of an except block — an alerting
    channel raising here would replace the real cause of the run's death."""
    deps = FakeDeps(explode=True)

    await debug_session._notify_crash(
        deps, INCIDENT_ID, "INC-2026-0001", "diagnosing", RuntimeError("provider timeout")
    )


async def test_unenqueued_incident_pages_even_when_the_db_write_fails(monkeypatch):
    """The transition and the page are independent: a status the DB refused
    to write is more worth a human's attention, not less."""

    @asynccontextmanager
    async def exploding_scope():
        raise LookupError("incident vanished")
        yield  # pragma: no cover

    monkeypatch.setattr(ingest, "session_scope", exploding_scope)
    deps = FakeDeps()

    await ingest._fail_unenqueued(deps, uuid.UUID(INCIDENT_ID), "INC-2026-0002", OSError("redis refused"))

    (message,) = deps.notifications.sent
    assert message.kind == "escalated"
    assert "never started" in message.title
    assert "OSError: redis refused" in message.body_markdown


async def test_unenqueued_without_a_deps_container_is_a_quiet_noop(monkeypatch):
    @asynccontextmanager
    async def exploding_scope():
        raise LookupError("incident vanished")
        yield  # pragma: no cover

    monkeypatch.setattr(ingest, "session_scope", exploding_scope)

    await ingest._fail_unenqueued(None, uuid.UUID(INCIDENT_ID), "INC-2026-0003", OSError("redis refused"))
