"""Prompt rendering is the model's entire view of the incident — these pin
the load-bearing sections (call chain, applied diff) so a refactor can't
silently drop them from the prompt."""

from __future__ import annotations

from uuid import uuid4

from haaland.domain.models import CodeLocation, Diagnosis, EvidenceBundle
from haaland.llm.rendering import render_diagnosis_input, render_test_input


def _bundle(**overrides) -> EvidenceBundle:
    defaults = dict(
        incident_id=uuid4(),
        service_name="orders-api",
        repo_full_name="acme/orders-api",
        base_ref="main",
    )
    return EvidenceBundle(**{**defaults, **overrides})


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        root_cause="average_item_price divides by len(items) without guarding empty carts.",
        category="logic_bug",
        confidence=0.9,
        culprit_locations=[
            CodeLocation(
                path="app/pricing.py", start_line=6, end_line=8,
                snippet="def average_item_price(...)", reason="traceback_frame", confidence=0.9,
            )
        ],
        supporting_evidence=[
            {"evidence_id": "e1", "excerpt": "ZeroDivisionError", "why_relevant": "raise site"}
        ],
        recommended_strategy="code_fix",
        strategy_rationale="Guard the empty list.",
    )


def test_diagnosis_input_includes_call_chain():
    bundle = _bundle(call_chain=["quote", "apply_discount", "average_item_price"])
    rendered = render_diagnosis_input(bundle)
    assert "quote -> apply_discount -> average_item_price" in rendered


def test_diagnosis_input_marks_missing_call_chain():
    rendered = render_diagnosis_input(_bundle())
    assert "(no traceback frames)" in rendered


def test_diagnosis_input_includes_deploy_context():
    entry = "- abc123def456 2026-08-20 <PERSON_1>: fix pool sizing\n  files: app/pool.py"
    bundle = _bundle(deploy_context=[{"rendered": entry}])
    rendered = render_diagnosis_input(bundle)
    assert "## Recent deployment context" in rendered
    assert "fix pool sizing" in rendered


def test_diagnosis_input_marks_cold_start_and_appends_orientation():
    rendered = render_diagnosis_input(_bundle(), orientation="### Repository tree (depth 2)\napp/")
    assert "localization is part" in rendered  # zero candidates named explicitly
    assert "## Repository orientation (deterministic seed)" in rendered
    assert "### Repository tree (depth 2)" in rendered


def test_test_input_includes_applied_diff():
    rendered = render_test_input(
        _diagnosis(), "Guard empty carts", ["app/pricing.py"],
        combined_patch="--- a/app/pricing.py\n+++ b/app/pricing.py\n+    if not items:\n+        return 0.0",
    )
    assert "## Applied diff" in rendered
    assert "if not items:" in rendered


def test_test_input_omits_diff_section_when_no_patch():
    rendered = render_test_input(_diagnosis(), "Guard empty carts", ["app/pricing.py"])
    assert "## Applied diff" not in rendered
