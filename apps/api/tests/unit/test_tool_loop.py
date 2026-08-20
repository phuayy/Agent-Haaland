"""ToolLoopService against a scripted provider: the loop's guarantees —
results fed back redacted, iteration ceiling enforced, every turn recorded
and charged, refusal surfacing — hold regardless of which real provider
sits behind the Protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from haaland.domain.errors import AIRefusalError
from haaland.domain.models import Diagnosis
from haaland.llm.base import LLMResult, Usage
from haaland.llm.tools import (
    AssistantTurn,
    ToolCall,
    ToolLoopRequest,
    ToolTurnResult,
    supports_tool_loop,
)
from haaland.services.code_toolbox import CodeToolbox
from haaland.services.tool_loop_service import ToolLoopService
from haaland.services.workspace_service import Workspace

_INCIDENT_ID = uuid4()

_DIAGNOSIS = Diagnosis(
    root_cause="Scripted diagnosis for tool-loop tests.",
    category="logic_bug",
    confidence=0.9,
    culprit_locations=[],
    supporting_evidence=[
        {"evidence_id": "scripted", "excerpt": "n/a", "why_relevant": "scripted output"}
    ],
    recommended_strategy="code_fix",
    strategy_rationale="Scripted.",
)


def _result(*, parsed: Any = None, stop_reason: str = "end_turn") -> LLMResult:
    return LLMResult(
        parsed=parsed,
        stop_reason=stop_reason,
        usage=Usage(input_tokens=100, output_tokens=50),
        cost_usd=0.01,
        latency_ms=1,
        model="scripted-model",
        provider="scripted",
    )


class ScriptedProvider:
    """Implements the ToolCallingLLMProvider Protocol by replaying `turns`;
    if the script runs out (iteration-ceiling tests) the last turn repeats.
    Captures every request for assertions."""

    name = "scripted"

    def __init__(self, turns: list[AssistantTurn], *, refuse_on_explore: bool = False) -> None:
        self._turns = list(turns)
        self._refuse_on_explore = refuse_on_explore
        self.explore_requests: list[ToolLoopRequest] = []
        self.conclude_request: ToolLoopRequest | None = None

    async def explore(self, request: ToolLoopRequest) -> ToolTurnResult:
        self.explore_requests.append(request)
        if self._refuse_on_explore:
            return ToolTurnResult(turn=AssistantTurn(text=""), result=_result(stop_reason="refusal"))
        turn = self._turns[min(len(self.explore_requests) - 1, len(self._turns) - 1)]
        stop_reason = "tool_use" if turn.tool_calls else "end_turn"
        return ToolTurnResult(turn=turn, result=_result(stop_reason=stop_reason))

    async def conclude(self, request: ToolLoopRequest) -> LLMResult:
        self.conclude_request = request
        return _result(parsed=_DIAGNOSIS)


class SpyAnalyses:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)


class SpyBudget:
    def __init__(self) -> None:
        self.charges: list[float] = []

    async def record_and_check(self, incident_id: Any, cost_usd: float) -> None:
        self.charges.append(cost_usd)


def _toolbox(tmp_path: Path) -> CodeToolbox:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "config.py").write_text(
        'ADMIN_CONTACT = "ops-admin@example.com"\nRETRIES = 3\n', encoding="utf-8"
    )
    workspace = Workspace(incident_id=_INCIDENT_ID, path=tmp_path, base_sha="deadbeef", repo=None)
    return CodeToolbox(workspace)


def _service(provider: ScriptedProvider, redactor, *, max_iterations: int = 12):
    analyses = SpyAnalyses()
    budget = SpyBudget()
    service = ToolLoopService(provider, analyses, budget, redactor, max_iterations=max_iterations)
    return service, analyses, budget


async def _run(service: ToolLoopService, toolbox: CodeToolbox):
    return await service.run(
        incident_id=_INCIDENT_ID,
        stage="diagnose",
        redacted_text="log lines here",
        output_schema=Diagnosis,
        toolbox=toolbox,
    )


async def test_loop_executes_calls_feeds_redacted_results_and_concludes(tmp_path, redactor):
    provider = ScriptedProvider(
        turns=[
            AssistantTurn(
                text="reading the config",
                tool_calls=(ToolCall(id="c1", name="read_file", arguments={"path": "app/config.py"}),),
            ),
            AssistantTurn(text="done exploring"),
        ]
    )
    service, analyses, budget = _service(provider, redactor)

    outcome = await _run(service, _toolbox(tmp_path))

    assert outcome.parsed is _DIAGNOSIS
    assert outcome.tool_calls == 1
    assert outcome.turns == 3  # two explore turns + conclusion

    # The second explore request carried the first turn's executed outcome,
    # redacted: the email became a token, never the raw value.
    second_request = provider.explore_requests[1]
    outcome_text = second_request.transcript[0].outcomes[0].content.text
    assert "ops-admin@example.com" not in outcome_text
    assert "<EMAIL_1>" in outcome_text
    assert "RETRIES = 3" in outcome_text  # non-PII content untouched

    # The conclusion saw the full transcript, closing reasoning included.
    assert provider.conclude_request is not None
    assert provider.conclude_request.transcript[-1].turn.text == "done exploring"

    # Every model turn was recorded and charged.
    assert [row["request_payload"]["phase"] for row in analyses.rows] == [
        "explore",
        "explore",
        "conclude",
    ]
    assert len(budget.charges) == 3


async def test_iteration_ceiling_forces_conclusion(tmp_path, redactor):
    greedy_turn = AssistantTurn(
        text="one more look",
        tool_calls=(ToolCall(id="c", name="list_dir", arguments={"path": "."}),),
    )
    provider = ScriptedProvider(turns=[greedy_turn])
    service, analyses, _budget = _service(provider, redactor, max_iterations=3)

    outcome = await _run(service, _toolbox(tmp_path))

    assert len(provider.explore_requests) == 3
    assert outcome.turns == 4
    assert analyses.rows[-1]["request_payload"]["phase"] == "conclude"


async def test_tool_errors_are_fed_back_not_raised(tmp_path, redactor):
    provider = ScriptedProvider(
        turns=[
            AssistantTurn(
                text="",
                tool_calls=(ToolCall(id="c1", name="read_file", arguments={"path": "../escape"}),),
            ),
            AssistantTurn(text="ok"),
        ]
    )
    service, _analyses, _budget = _service(provider, redactor)

    await _run(service, _toolbox(tmp_path))

    outcome = provider.explore_requests[1].transcript[0].outcomes[0]
    assert outcome.is_error
    assert "outside the workspace" in outcome.content.text


async def test_explore_refusal_raises_but_is_still_charged(tmp_path, redactor):
    provider = ScriptedProvider(turns=[AssistantTurn(text="")], refuse_on_explore=True)
    service, _analyses, budget = _service(provider, redactor)

    with pytest.raises(AIRefusalError):
        await _run(service, _toolbox(tmp_path))
    assert len(budget.charges) == 1


def test_capability_detection():
    provider = ScriptedProvider(turns=[])
    assert supports_tool_loop(provider)

    class NotToolCapable:
        name = "plain"

        async def generate(self, request):  # pragma: no cover — shape only
            raise NotImplementedError

    assert not supports_tool_loop(NotToolCapable())
