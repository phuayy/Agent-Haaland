"""Assembles, never writes, the post-mortem: the timeline table is rendered
directly from `incident_events`; the model supplies prose sections only and
is never asked to restate facts already held in structured form (docs/05)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from haaland.db.models.incident import Incident
from haaland.db.models.incident_event import IncidentEvent
from haaland.domain.models import PostmortemProse

_TEMPLATES_ROOT = Path(__file__).resolve().parents[3] / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_ROOT)), autoescape=select_autoescape())


class PostmortemService:
    def render(
        self,
        *,
        incident: Incident,
        events: list[IncidentEvent],
        prose: PostmortemProse,
        chain_verified: bool,
    ) -> str:
        template = _env.get_template("postmortem.md.j2")
        return template.render(
            incident=incident,
            events=events,
            summary_prose=prose.summary,
            root_cause_prose=prose.root_cause_narrative,
            resolution_prose=prose.resolution_narrative,
            went_well_prose=prose.went_well,
            went_wrong_prose=prose.went_wrong,
            action_items_prose="\n".join(f"- {item}" for item in prose.action_items) or "- none recorded",
            chain_verified=chain_verified,
        )

    def render_pr_body(
        self,
        *,
        incident_reference: str,
        dashboard_url: str,
        root_cause: str,
        confidence: float,
        body_markdown: str,
    ) -> str:
        template = _env.get_template("pr_body.md.j2")
        return template.render(
            incident={"reference": incident_reference},
            dashboard_url=dashboard_url,
            root_cause=root_cause,
            confidence=confidence,
            body_markdown=body_markdown,
        )
