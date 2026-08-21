"""Culprit hydration: the model emits path+span refs (DiagnosisDraft) and
the diagnose node reads the snippet out of the clone itself — a ref that
doesn't resolve is a detectable hallucination, dropped and reported, never
turned into a plausible-looking snippet."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from haaland.agent.nodes.diagnose import _hydrate_culprits
from haaland.domain.models import CodeLocation, CulpritLocationRef, EvidenceBundle
from haaland.services.workspace_service import Workspace

_SOURCE = "def acquire(pool):\n    if pool.exhausted:\n        raise TimeoutError\n    return pool.get()\n"


def _workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "pool.py").write_text(_SOURCE, encoding="utf-8")
    return Workspace(incident_id=uuid4(), path=tmp_path, base_sha="deadbeef", repo=None)


def _bundle(**overrides) -> EvidenceBundle:
    defaults = dict(
        incident_id=uuid4(), service_name="s", repo_full_name="acme/s", base_ref="main"
    )
    return EvidenceBundle(**{**defaults, **overrides})


def test_resolving_ref_gets_snippet_from_the_clone(tmp_path):
    refs = [CulpritLocationRef(path="app/pool.py", start_line=2, end_line=3)]

    hydrated, unresolved = _hydrate_culprits(refs, _workspace(tmp_path), _bundle())

    assert unresolved == []
    assert len(hydrated) == 1
    assert hydrated[0].snippet == "    if pool.exhausted:\n        raise TimeoutError"
    assert hydrated[0].reason == "model_identified"


def test_hallucinated_path_is_dropped_and_reported(tmp_path):
    refs = [CulpritLocationRef(path="app/invented.py", start_line=1, end_line=5)]

    hydrated, unresolved = _hydrate_culprits(refs, _workspace(tmp_path), _bundle())

    assert hydrated == []
    assert unresolved == ["app/invented.py:1-5"]


def test_span_past_end_of_file_is_reported_not_fabricated(tmp_path):
    refs = [CulpritLocationRef(path="app/pool.py", start_line=100, end_line=120)]

    hydrated, unresolved = _hydrate_culprits(refs, _workspace(tmp_path), _bundle())

    assert hydrated == []
    assert unresolved and "past end of file" in unresolved[0]


def test_without_workspace_falls_back_to_located_candidates(tmp_path):
    candidate = CodeLocation(
        path="app/pool.py", start_line=1, end_line=4, snippet=_SOURCE.strip(),
        reason="traceback_frame", confidence=0.9,
    )
    refs = [
        CulpritLocationRef(path="app/pool.py", start_line=2, end_line=3),
        CulpritLocationRef(path="app/other.py", start_line=1, end_line=2),
    ]

    hydrated, unresolved = _hydrate_culprits(refs, None, _bundle(code_candidates=[candidate]))

    assert hydrated == [candidate]
    assert unresolved == ["app/other.py:1-2"]
