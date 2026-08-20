"""Alertmanager → debug-session mapping. The webhook is the production
trigger surface, so the contract it enforces (bearer auth, repo_url
required, resolved notifications ignored, retries deduped) is pinned here
against a fixed payload rather than discovered during an incident."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from haaland.api.webhooks import alertmanager
from haaland.config import Settings

TOKEN = "test-alertmanager-token"


def _payload(**overrides) -> dict:
    payload = {
        "version": "4",
        "groupKey": '{}:{alertname="HighErrorRate"}',
        "status": "firing",
        "receiver": "haaland",
        "externalURL": "http://prometheus.example/alertmanager",
        "groupLabels": {"alertname": "HighErrorRate"},
        "commonLabels": {"alertname": "HighErrorRate", "service": "payments-api", "severity": "critical"},
        "commonAnnotations": {"repo_url": "https://github.com/acme/payments-api"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighErrorRate", "pod": "payments-api-7d9f"},
                "annotations": {"summary": "5xx rate above 10%", "description": "pool exhausted"},
                "startsAt": "2026-08-15T09:12:03.117Z",
                "generatorURL": "http://prometheus.example/graph?g0.expr=...",
                "fingerprint": "8f21c0aa",
            }
        ],
    }
    payload.update(overrides)
    return payload


class FakeArqPool:
    """`set` is the dedupe claim (Redis SET NX), `enqueue_job` the handoff to
    the worker. Both are all the handler touches."""

    def __init__(self, *, claim: bool = True) -> None:
        self._claim = claim
        self.jobs: list[tuple] = []
        self.set_calls: list[str] = []

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        self.set_calls.append(key)
        return self._claim

    async def enqueue_job(self, name: str, *args):
        self.jobs.append((name, args))


@pytest.fixture
def client_factory(monkeypatch):
    def _build(pool: FakeArqPool):
        launched: list = []

        async def fake_launch(request, arq_pool):
            launched.append(request)
            await arq_pool.enqueue_job("run_debug_session", request.repo_url)
            return "INC-2026-0001", "11111111-1111-1111-1111-111111111111"

        monkeypatch.setattr(alertmanager, "launch_debug_session", fake_launch)

        settings = Settings(
            llm_provider="fake",
            model_primary="fake",
            model_cheap="fake",
            model_report="fake",
            alertmanager_webhook_token=TOKEN,
        )
        app = FastAPI()
        app.include_router(alertmanager.router)
        app.state.deps = type("D", (), {"settings": settings})()
        app.state.arq_pool = pool
        return TestClient(app), launched

    return _build


def _post(client, payload, token: str | None = TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/webhooks/alertmanager", json=payload, headers=headers)


def test_rejects_missing_token(client_factory):
    client, _ = client_factory(FakeArqPool())
    assert _post(client, _payload(), token=None).status_code == 401


def test_rejects_wrong_token(client_factory):
    client, _ = client_factory(FakeArqPool())
    assert _post(client, _payload(), token="nope").status_code == 401


def test_firing_alert_launches_a_debug_session(client_factory):
    pool = FakeArqPool()
    client, launched = client_factory(pool)

    response = _post(client, _payload())

    assert response.status_code == 202
    assert response.json()["reference"] == "INC-2026-0001"
    assert len(launched) == 1
    request = launched[0]
    assert request.repo_url == "https://github.com/acme/payments-api"
    assert request.service_name == "payments-api"
    assert request.base_ref == "main"
    # The evidence blob must carry what a human would need to triage.
    assert "HighErrorRate" in request.log_text
    assert "5xx rate above 10%" in request.log_text
    assert "payments-api-7d9f" in request.log_text
    assert pool.jobs


def test_repo_ref_annotation_overrides_default_branch(client_factory):
    client, launched = client_factory(FakeArqPool())
    payload = _payload(commonAnnotations={
        "repo_url": "https://github.com/acme/payments-api", "repo_ref": "release/2026-08"
    })

    assert _post(client, payload).status_code == 202
    assert launched[0].base_ref == "release/2026-08"


def test_alert_scoped_annotation_beats_group_scoped(client_factory):
    client, launched = client_factory(FakeArqPool())
    payload = _payload()
    payload["alerts"][0]["annotations"]["repo_url"] = "https://github.com/acme/override-repo"

    assert _post(client, payload).status_code == 202
    assert launched[0].repo_url == "https://github.com/acme/override-repo"


def test_missing_repo_url_is_rejected_not_silently_dropped(client_factory):
    client, launched = client_factory(FakeArqPool())
    payload = _payload(commonAnnotations={})

    response = _post(client, payload)

    assert response.status_code == 422
    assert "repo_url" in response.json()["detail"]
    assert launched == []


def test_resolved_notification_is_ignored(client_factory):
    client, launched = client_factory(FakeArqPool())

    response = _post(client, _payload(status="resolved"))

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert launched == []


def test_group_with_no_firing_alerts_is_ignored(client_factory):
    client, launched = client_factory(FakeArqPool())
    payload = _payload()
    payload["alerts"][0]["status"] = "resolved"

    assert _post(client, payload).json()["status"] == "ignored"
    assert launched == []


def test_repeat_delivery_is_deduplicated(client_factory):
    pool = FakeArqPool(claim=False)
    client, launched = client_factory(pool)

    response = _post(client, _payload())

    assert response.status_code == 202
    assert response.json()["status"] == "deduplicated"
    assert launched == []
    assert pool.set_calls == ['dedupe:alertmanager:{}:{alertname="HighErrorRate"}']


def test_service_name_falls_back_to_job_then_alertname(client_factory):
    client, launched = client_factory(FakeArqPool())
    payload = _payload(commonLabels={"alertname": "HighErrorRate", "job": "checkout"})

    assert _post(client, payload).status_code == 202
    assert launched[0].service_name == "checkout"
