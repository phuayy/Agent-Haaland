"""docs/09 layer 1: path traversal and the protected-path denylist are
enforced in code, after the model's output is parsed — the schema alone
(no `delete`/`execute` action) isn't sufficient, since it can't stop a
`.github/workflows/deploy.yml` edit or a `../../etc/passwd` path."""

from __future__ import annotations

from uuid import uuid4

import pytest

from haaland.domain.errors import RemediationRejected
from haaland.domain.models import FileChange
from haaland.services.patch_service import apply_changes, validate_file_change
from haaland.services.workspace_service import Workspace


def _workspace(tmp_path) -> Workspace:
    return Workspace(incident_id=uuid4(), path=tmp_path, base_sha="deadbeef", repo=None)


def test_path_traversal_rejected(tmp_path):
    fc = FileChange(path="../../etc/passwd", action="modify", new_content="x", change_summary="s")
    with pytest.raises(RemediationRejected, match="traversal"):
        validate_file_change(fc, _workspace(tmp_path))


def test_workflow_file_rejected(tmp_path):
    fc = FileChange(
        path=".github/workflows/deploy.yml", action="modify", new_content="x", change_summary="s"
    )
    with pytest.raises(RemediationRejected, match="protected path"):
        validate_file_change(fc, _workspace(tmp_path))


def test_dotenv_rejected(tmp_path):
    fc = FileChange(path=".env.production", action="modify", new_content="x", change_summary="s")
    with pytest.raises(RemediationRejected, match="protected path"):
        validate_file_change(fc, _workspace(tmp_path))


def test_revert_of_nonexistent_file_rejected(tmp_path):
    fc = FileChange(path="app/does_not_exist.py", action="revert", new_content="x", change_summary="s")
    with pytest.raises(RemediationRejected, match="non-existent"):
        validate_file_change(fc, _workspace(tmp_path))


def test_ordinary_source_file_accepted(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "pricing.py").write_text("x = 1\n")
    fc = FileChange(path="app/pricing.py", action="modify", new_content="x = 2\n", change_summary="fix")
    validate_file_change(fc, _workspace(tmp_path))  # must not raise


def test_apply_changes_writes_file_and_returns_diff(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "pricing.py").write_text("x = 1\n")
    workspace = _workspace(tmp_path)
    fc = FileChange(path="app/pricing.py", action="modify", new_content="x = 2\n", change_summary="fix")

    diffs = apply_changes([fc], workspace)

    assert (tmp_path / "app" / "pricing.py").read_text() == "x = 2\n"
    assert "app/pricing.py" in diffs
    assert "-x = 1" in diffs["app/pricing.py"]
    assert "+x = 2" in diffs["app/pricing.py"]


def test_more_than_ten_files_rejected(tmp_path):
    workspace = _workspace(tmp_path)
    files = [
        FileChange(path=f"app/f{i}.py", action="modify", new_content="x = 1\n", change_summary="s")
        for i in range(11)
    ]
    with pytest.raises(RemediationRejected, match="ceiling"):
        apply_changes(files, workspace)
