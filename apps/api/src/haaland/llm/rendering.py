"""Evidence bundle / intermediate results -> prompt text. Kept separate from
the nodes so the exact rendering is unit-testable without a model call, and
separate from the providers so it stays provider-neutral — only the vendor
envelope (llm/providers/*) differs per provider, never this text."""

from __future__ import annotations

import json

from haaland.domain.models import Diagnosis, EvidenceBundle, FixEvaluation


def render_classify_input(bundle: EvidenceBundle) -> str:
    lines = "\n".join(f"[{ln.level}] {ln.message}" for ln in bundle.log_lines[:200])
    return (
        f"Service: {bundle.service_name}\nRepository: {bundle.repo_full_name}\n\n"
        f"## Log lines ({len(bundle.log_lines)} total, showing up to 200)\n{lines}"
    )


def render_diagnosis_input(bundle: EvidenceBundle) -> str:
    log_lines = "\n".join(f"[{ln.level}] {ln.message}" for ln in bundle.log_lines[:200])
    candidates = "\n\n".join(
        f"### Candidate {i} — {c.path}:{c.start_line}-{c.end_line} "
        f"(reason={c.reason}, confidence={c.confidence:.2f})\n```\n{c.snippet}\n```"
        for i, c in enumerate(bundle.code_candidates)
    )
    return (
        f"Service: {bundle.service_name}\nRepository: {bundle.repo_full_name}\n\n"
        f"## Log lines\n{log_lines}\n\n## Code candidates\n{candidates or '(none located)'}"
    )


def render_evaluate_input(
    diagnosis: Diagnosis, previous_failure_detail: str | None = None, attempt: int = 1
) -> str:
    body = (
        f"## Diagnosis (confidence {diagnosis.confidence:.2f})\n{diagnosis.root_cause}\n\n"
        f"Category: {diagnosis.category}\nRecommended strategy: {diagnosis.recommended_strategy}\n"
        f"Rationale: {diagnosis.strategy_rationale}\n\n"
        f"## Culprit locations\n"
        + "\n".join(f"- {c.path}:{c.start_line}-{c.end_line}" for c in diagnosis.culprit_locations)
    )
    if previous_failure_detail:
        body += (
            f"\n\n## Retry — attempt {attempt}\nThe previous candidate failed verification:\n"
            f"```\n{previous_failure_detail[:2000]}\n```"
        )
    return body


def render_remediate_input(diagnosis: Diagnosis, evaluation: FixEvaluation) -> str:
    selected = evaluation.candidates[evaluation.selected_index]
    culprit = "\n".join(
        f"### {c.path}:{c.start_line}-{c.end_line}\n```\n{c.snippet}\n```"
        for c in diagnosis.culprit_locations
    )
    return (
        f"## Selected fix\n{selected.summary}\nApproach: {selected.approach}\nRisk: {selected.risk}\n\n"
        f"## Root cause\n{diagnosis.root_cause}\n\n## Files to consider\n{culprit or '(none)'}"
    )


def render_test_input(diagnosis: Diagnosis, fix_summary: str, changed_paths: list[str]) -> str:
    return (
        f"## Failure scenario\n{diagnosis.root_cause}\n\n## Applied fix\n{fix_summary}\n\n"
        f"## Changed files\n" + "\n".join(f"- {p}" for p in changed_paths)
    )


def render_report_input(incident_summary: dict, events: list[dict]) -> str:
    return (
        f"## Incident\n{json.dumps(incident_summary, default=str, indent=2)}\n\n"
        f"## Event timeline (do not restate verbatim — narrate around it)\n"
        f"{json.dumps(events, default=str, indent=2)}"
    )
