from __future__ import annotations

from uuid import uuid4

import pytest

from haaland.services.workspace_service import Workspace


def _workspace(tmp_path) -> Workspace:
    return Workspace(incident_id=uuid4(), path=tmp_path, base_sha="deadbeef", repo=None)


def test_read_outside_workspace_returns_none(tmp_path):
    (tmp_path.parent / "outside.txt").write_text("secret")
    assert _workspace(tmp_path).read_file("../outside.txt") is None


def test_write_outside_workspace_raises(tmp_path):
    with pytest.raises(ValueError, match="escapes workspace"):
        _workspace(tmp_path).write_file("../evil.txt", "x")


def test_sibling_prefix_dir_is_not_inside(tmp_path):
    """The bug a string startswith() check has: /ws-evil 'starts with' /ws.
    is_relative_to must reject it."""
    evil_sibling = tmp_path.parent / (tmp_path.name + "-evil")
    evil_sibling.mkdir()
    (evil_sibling / "f.txt").write_text("x")

    ws = _workspace(tmp_path)
    assert ws.read_file(f"../{evil_sibling.name}/f.txt") is None


def test_normal_relative_read_write_roundtrip(tmp_path):
    ws = _workspace(tmp_path)
    ws.write_file("app/sub/file.py", "x = 1\n")
    assert ws.read_file("app/sub/file.py") == "x = 1\n"
