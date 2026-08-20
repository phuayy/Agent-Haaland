"""The alert-triggered detection path from docs/01 Stage 1.

Prometheus evaluates a rule, Alertmanager groups the firing alerts and POSTs
its v4 webhook payload here. This handler follows docs/04's five-step
contract — verify, validate, persist, enqueue, return 2xx fast — and does no
analysis of its own; the LangGraph run happens in the worker.

Alertmanager sends a fixed payload shape and offers no request-body
templating, so the repository under investigation has to travel as alert
metadata. The convention is a `repo_url` annotation on the alerting rule
(falling back to a label of the same name), which keeps the routing decision
next to the rule that fires it rather than in a translation layer nobody
owns.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from haaland.api.deps import get_arq_pool, get_deps
from haaland.api.ingest import launch_debug_session
from haaland.api.webhooks.signature import verify_bearer
from haaland.domain.models import DebugSessionRequest
from haaland.logging import get_logger

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

logger = get_logger(__name__)

# Order matters: the first key present wins. `service` is the Prometheus
# convention; `job` is what a scrape config supplies when nothing else does.
_SERVICE_KEYS = ("service", "service_name", "job", "alertname")
_MAX_ALERTS_RENDERED = 20


def _lookup(payload: dict[str, Any], alert: dict[str, Any], key: str) -> str | None:
    """Resolve a key from the most specific scope outwards: the individual
    alert's annotations/labels, then the group's common ones."""
    for scope in (
        alert.get("annotations"),
        alert.get("labels"),
        payload.get("commonAnnotations"),
        payload.get("commonLabels"),
        payload.get("groupLabels"),
    ):
        if isinstance(scope, dict):
            value = scope.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _render_log_text(payload: dict[str, Any], alerts: list[dict[str, Any]]) -> str:
    """Flatten the alert group into the plain-text evidence blob the pipeline
    already consumes. Everything here is untrusted input and crosses the
    redaction boundary in the graph's redact node, same as pasted logs."""
    lines: list[str] = []
    status = payload.get("status", "firing")
    lines.append(f"# Alertmanager group ({status}) — {len(alerts)} alert(s)")
    if external_url := payload.get("externalURL"):
        lines.append(f"# source: {external_url}")

    for alert in alerts[:_MAX_ALERTS_RENDERED]:
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        lines.append("")
        lines.append(f"## {labels.get('alertname', 'alert')} [{alert.get('status', status)}]")
        if starts_at := alert.get("startsAt"):
            lines.append(f"startsAt: {starts_at}")
        for key in ("summary", "description", "message", "runbook_url"):
            if value := annotations.get(key):
                lines.append(f"{key}: {value}")
        remaining = {k: v for k, v in annotations.items()
                     if k not in {"summary", "description", "message", "runbook_url", "repo_url", "repo_ref"}}
        if remaining:
            lines.append(f"annotations: {json.dumps(remaining, sort_keys=True)}")
        if labels:
            lines.append(f"labels: {json.dumps(labels, sort_keys=True)}")
        if generator_url := alert.get("generatorURL"):
            lines.append(f"generatorURL: {generator_url}")

    if len(alerts) > _MAX_ALERTS_RENDERED:
        lines.append("")
        lines.append(f"... {len(alerts) - _MAX_ALERTS_RENDERED} further alert(s) omitted")

    return "\n".join(lines)


@router.post("/alertmanager", status_code=202)
async def alertmanager_webhook(
    request: Request, deps=Depends(get_deps), arq_pool=Depends(get_arq_pool)
) -> dict:
    if not verify_bearer(deps.settings.alertmanager_webhook_token, request.headers.get("authorization")):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="expected an Alertmanager webhook object")

    # A resolved notification is the all-clear for an alert we already acted
    # on; re-running the pipeline on it would open a second incident for a
    # problem that just stopped happening.
    if payload.get("status") == "resolved":
        return {"status": "ignored", "reason": "resolved notification"}

    alerts = [a for a in (payload.get("alerts") or []) if isinstance(a, dict)]
    firing = [a for a in alerts if a.get("status", "firing") == "firing"]
    if not firing:
        return {"status": "ignored", "reason": "no firing alerts in group"}

    first = firing[0]

    repo_url = _lookup(payload, first, "repo_url")
    if not repo_url:
        # Persisting nothing is the honest outcome here: without a repository
        # there is no workspace to clone and no diff to propose. Fail loudly
        # so the rule author sees it in Alertmanager's notification log
        # rather than discovering months later that alerts vanished.
        raise HTTPException(
            status_code=422,
            detail="alert carries no `repo_url` annotation or label; add one to the "
            "Prometheus alerting rule so Haaland knows which repository to debug",
        )

    service_name = next(
        (value for key in _SERVICE_KEYS if (value := _lookup(payload, first, key))),
        "unknown-service",
    )
    base_ref = _lookup(payload, first, "repo_ref") or "main"

    # Alertmanager retries on any non-2xx and re-sends on its repeat_interval;
    # both would otherwise open a fresh incident for the same firing group.
    dedupe_key = payload.get("groupKey") or first.get("fingerprint") or f"{repo_url}:{service_name}"
    claimed = await arq_pool.set(
        f"dedupe:alertmanager:{dedupe_key}",
        "1",
        ex=deps.settings.dedupe_window_seconds,
        nx=True,
    )
    if not claimed:
        logger.info("alertmanager alert deduped", dedupe_key=dedupe_key, service_name=service_name)
        return {"status": "deduplicated", "dedupe_key": dedupe_key}

    session_request = DebugSessionRequest(
        repo_url=repo_url,
        service_name=service_name,
        log_text=_render_log_text(payload, firing),
        base_ref=base_ref,
    )

    try:
        reference, incident_id = await launch_debug_session(session_request, arq_pool)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "alertmanager alert ingested",
        reference=reference,
        service_name=service_name,
        repo_url=repo_url,
        alert_count=len(firing),
    )
    return {"reference": reference, "incident_id": incident_id, "status": "detected"}
