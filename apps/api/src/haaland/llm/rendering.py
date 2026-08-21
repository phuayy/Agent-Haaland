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


def format_recent_commits(commits: list[dict]) -> str:
    """Workspace.recent_commits() -> the deploy-context prompt section. Kept
    here (not in the node) so the exact rendering is unit-testable."""
    parts = []
    for c in commits:
        files = ", ".join(c.get("files", [])[:20]) or "(file list unavailable)"
        parts.append(
            f"- {c.get('sha', '?')} {c.get('date', '')} {c.get('author', '')}: "
            f"{c.get('message', '')}\n  files: {files}"
        )
    return "\n".join(parts)


def _deploy_context_section(bundle: EvidenceBundle) -> str:
    if not bundle.deploy_context:
        return "(none available)"
    rendered = []
    for entry in bundle.deploy_context:
        if isinstance(entry, dict) and "rendered" in entry:
            rendered.append(str(entry["rendered"]))
        else:
            rendered.append(json.dumps(entry, default=str))
    return "\n".join(rendered)


_NO_CANDIDATES = (
    "(none located — no traceback frame or error-message literal matched this "
    "repository; no location was pre-ranked for you, and localization is part "
    "of your job)"
)


def render_diagnosis_input(bundle: EvidenceBundle, orientation: str | None = None) -> str:
    log_lines = "\n".join(f"[{ln.level}] {ln.message}" for ln in bundle.log_lines[:200])
    candidates = "\n\n".join(
        f"### Candidate {i} — {c.path}:{c.start_line}-{c.end_line} "
        f"(reason={c.reason}, confidence={c.confidence:.2f})\n```\n{c.snippet}\n```"
        for i, c in enumerate(bundle.code_candidates)
    )
    chain = " -> ".join(bundle.call_chain)
    body = (
        f"Service: {bundle.service_name}\nRepository: {bundle.repo_full_name}\n\n"
        f"## Log lines\n{log_lines}\n\n"
        f"## Failure call chain (outermost first)\n{chain or '(no traceback frames)'}\n\n"
        f"## Recent deployment context (commits on {bundle.base_ref})\n"
        f"{_deploy_context_section(bundle)}\n\n"
        f"## Code candidates\n{candidates or _NO_CANDIDATES}"
    )
    if orientation:
        body += f"\n\n## Repository orientation (deterministic seed)\n{orientation}"
    return body


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


def render_test_input(
    diagnosis: Diagnosis, fix_summary: str, changed_paths: list[str], combined_patch: str | None = None
) -> str:
    body = (
        f"## Failure scenario\n{diagnosis.root_cause}\n\n## Applied fix\n{fix_summary}\n\n"
        f"## Changed files\n" + "\n".join(f"- {p}" for p in changed_paths)
    )
    if combined_patch:
        # The diff is the ground truth the smoke test must exercise — without
        # it the model tests the root-cause *description*, not the code.
        body += f"\n\n## Applied diff\n```diff\n{combined_patch[:8000]}\n```"
    return body


def render_report_input(incident_summary: dict, events: list[dict]) -> str:
    return (
        f"## Incident\n{json.dumps(incident_summary, default=str, indent=2)}\n\n"
        f"## Event timeline (do not restate verbatim — narrate around it)\n"
        f"{json.dumps(events, default=str, indent=2)}"
    )
