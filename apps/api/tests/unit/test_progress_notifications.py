"""The in-flight pings. The outcome cards are covered elsewhere
(test_failure_notifications.py, test_lark_notifier.py) — what these tests
protect is the other half of the contract: that a heartbeat stays a
heartbeat. It must not ask for a click, must not wear a P1's colour, must
not fire once per retry, and must never take a run down with it."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest

from haaland.agent.nodes import _progress, evaluate_fixes
from haaland.config import Settings
from haaland.domain.enums import Severity
from haaland.domain.models import Classification, Diagnosis, FixCandidate, FixEvaluation
from haaland.integrations.notify.lark import build_card
from haaland.services.progress_service import progress_message

INCIDENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


class RecordingNotifications:
    def __init__(self, *, explode: bool = False) -> None:
        self.sent: list = []
        self._explode = explode

    async def broadcast(self, message):
        if self._explode:
            raise RuntimeError("the notifier itself is broken")
        self.sent.append(message)
        return []


class FakeDeps:
    def __init__(self, *, explode: bool = False, **settings) -> None:
        self.notifications = RecordingNotifications(explode=explode)
        # _env_file=None keeps the developer's own .env out of the assertions.
        self.settings = Settings(_env_file=None, **settings)
        self.llm = type("LLM", (), {"name": "fake"})()


def _state(**overrides) -> dict:
    state = {
        "incident_id": INCIDENT_ID,
        "reference": "INC-2026-0001",
        "service_name": "payments-api",
    }
    state.update(overrides)
    return state


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        root_cause="connection pool exhausted under retry storm",
        category="resource_exhaustion",
        confidence=0.82,
        supporting_evidence=[{"evidence_id": "e1", "excerpt": "x", "why_relevant": "y"}],
        recommended_strategy="code_fix",
        strategy_rationale="raise the ceiling and bound the retries",
    )


@pytest.fixture
def no_db(monkeypatch):
    """The ping path opens a session only to write its delivery rows; these
    tests are about what gets sent, not what gets written."""

    async def _noop(**kwargs):
        return None

    @asynccontextmanager
    async def fake_context(deps):
        yield type("Ctx", (), {"notifications": type("N", (), {"record": _noop})()})()

    monkeypatch.setattr(_progress, "node_context", fake_context)


# --------------------------------------------------------------- wording


@pytest.mark.parametrize("stage", ["accepted", "diagnosing", "fixing"])
def test_every_stage_is_addressed_to_the_incident_and_asks_for_nothing(stage):
    message = progress_message(
        stage, reference="INC-2026-0001", service_name="payments-api", severity=Severity.P1
    )

    assert message.kind == "progress"
    assert message.title.startswith("[INC-2026-0001] ")
    assert message.incident_reference == "INC-2026-0001"
    assert "payments-api" in message.body_markdown
    # A heartbeat with a button competes with the two cards that need a click.
    assert message.links == {}
    assert message.mentions == []


def test_detail_line_is_rendered_above_the_stage_line():
    message = progress_message(
        "fixing",
        reference="INC-2026-0001",
        service_name="payments-api",
        detail="**Root cause:** pool exhausted",
    )

    body = message.body_markdown
    assert "**Root cause:** pool exhausted" in body
    assert body.index("pool exhausted") < body.index("Drafting a patch")


# ----------------------------------------------------------------- card


def test_progress_card_stays_blue_even_on_a_p1():
    """Severity colours the in-flight outcome cards; a heartbeat wearing red
    teaches the channel to read urgency into a card that asks for nothing."""
    card = build_card(
        progress_message(
            "diagnosing",
            reference="INC-2026-0001",
            service_name="payments-api",
            severity=Severity.P1,
        )
    )

    assert card["header"]["template"] == "blue"
    assert not [e for e in card["elements"] if e["tag"] == "action"]


# ------------------------------------------------------------- delivery


async def test_disabled_progress_sends_nothing(no_db):
    deps = FakeDeps(notify_progress=False)

    await _progress.announce_progress(_state(), deps, "accepted")

    assert deps.notifications.sent == []


async def test_a_broken_notifier_never_fails_the_run(no_db):
    """NotificationService absorbs a channel raising NotificationError; it
    does not absorb an adapter (or this module) raising anything else."""
    deps = FakeDeps(explode=True)

    await _progress.announce_progress(_state(), deps, "accepted")  # must not raise


async def test_severity_rides_along_when_the_incident_is_classified(no_db):
    deps = FakeDeps()

    await _progress.announce_progress(_state(), deps, "diagnosing", severity=Severity.P2)

    assert deps.notifications.sent[0].severity == Severity.P2


# ------------------------------------------------------------ anti-spam


def _evaluate_fixes_context(monkeypatch):
    """Enough of a NodeContext for evaluate_fixes_node to run offline."""

    class FakeLLMCall:
        async def call(self, **kwargs):
            return FixEvaluation(
                candidates=[
                    FixCandidate(
                        summary="bound the retries", approach="a", risk="low", rationale="r"
                    )
                ],
                selected_index=0,
                selection_rationale="cheapest reversible change",
            )

    class FakeAudit:
        async def record(self, *args, **kwargs):
            return None

    class FakeIncidents:
        async def get(self, incident_id):
            return None

    class FakeIncidentService:
        async def transition(self, *args, **kwargs):
            return None

    @asynccontextmanager
    async def fake_context(deps):
        yield type(
            "Ctx",
            (),
            {
                "llm_call": FakeLLMCall(),
                "audit": FakeAudit(),
                "incidents": FakeIncidents(),
                "incident_service": FakeIncidentService(),
            },
        )()

    monkeypatch.setattr(evaluate_fixes, "node_context", fake_context)


async def test_the_fix_loop_announces_once_and_then_stays_quiet(monkeypatch, no_db):
    """evaluate_fixes is re-entered on every failed check, every failed test
    run and every human rejection. One incident must not become five
    identical cards."""
    _evaluate_fixes_context(monkeypatch)
    deps = FakeDeps()
    state = _state(
        diagnosis=_diagnosis(),
        classification=Classification(
            severity=Severity.P2,
            confidence=0.9,
            customer_impact="degraded",
            affected_services=["payments-api"],
            blast_radius_estimate="one service",
            rationale="checkout latency",
            requires_immediate_page=False,
        ),
        fix_attempt=0,
    )

    for _ in range(3):  # first draft, then two retries
        patch = await evaluate_fixes.evaluate_fixes_node(state, deps)
        state.update(patch)

    assert state["fix_attempt"] == 3
    assert len(deps.notifications.sent) == 1
    sent = deps.notifications.sent[0]
    assert sent.title == "[INC-2026-0001] Debugging"
    assert "connection pool exhausted" in sent.body_markdown
    assert sent.severity == Severity.P2
