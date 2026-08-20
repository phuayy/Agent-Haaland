"""The toolbox is the model-facing attack surface of the exploration loop:
these tests pin the three invariants (containment, bounded output,
correctable errors) rather than the cosmetic output shape."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from haaland.llm.tools import ToolCall
from haaland.services.code_toolbox import CodeToolbox
from haaland.services.workspace_service import Workspace

_PRICING_SOURCE = '''"""Pricing helpers."""


def average_item_price(items: list[dict]) -> float:
    total = sum(item["price"] for item in items)
    return total / len(items)


def apply_discount(items: list[dict], discount_pct: float) -> float:
    avg_price = average_item_price(items)
    return avg_price * (1 - discount_pct / 100)
'''


def _toolbox(tmp_path: Path) -> CodeToolbox:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "pricing.py").write_text(_PRICING_SOURCE, encoding="utf-8")
    (app_dir / "config.yaml").write_text("discount_pct: 10\n", encoding="utf-8")
    (tmp_path / "asset.bin").write_bytes(b"\x00\x01\x02binary")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n", encoding="utf-8")
    workspace = Workspace(incident_id=uuid4(), path=tmp_path, base_sha="deadbeef", repo=None)
    return CodeToolbox(workspace)


def _run(toolbox: CodeToolbox, tool: str, **arguments) -> tuple[str, bool]:
    return toolbox.execute(ToolCall(id="t1", name=tool, arguments=arguments))


def test_specs_cover_every_tool_with_schemas(tmp_path):
    specs = _toolbox(tmp_path).specs()
    names = {s.name for s in specs}
    assert names == {"grep", "read_file", "glob", "list_dir", "find_symbol"}
    assert all(s.input_schema.get("type") == "object" for s in specs)
    assert all(s.description for s in specs)


def test_grep_returns_path_line_matches(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "grep", pattern=r"len\(items\)")
    assert not is_error
    assert "app/pricing.py:6:" in content
    assert "return total / len(items)" in content


def test_grep_glob_filter_excludes_other_files(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "grep", pattern="discount", glob="*.yaml")
    assert not is_error
    assert "config.yaml" in content
    assert "pricing.py" not in content


def test_grep_caps_matches(tmp_path):
    (tmp_path / "noise.txt").write_text("needle\n" * 300, encoding="utf-8")
    content, is_error = _run(_toolbox(tmp_path), "grep", pattern="needle", max_matches=10)
    assert not is_error
    assert content.count("noise.txt") == 10
    assert "stopped at 10 matches" in content


def test_grep_invalid_regex_is_correctable_error(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "grep", pattern="(unclosed")
    assert is_error
    assert "invalid regular expression" in content


def test_grep_skips_binary_and_git_internals(tmp_path):
    content, _ = _run(_toolbox(tmp_path), "grep", pattern="binary|core")
    assert "asset.bin" not in content
    assert ".git" not in content


def test_read_file_numbers_lines_and_pages(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "read_file", path="app/pricing.py", offset=4, limit=2)
    assert not is_error
    assert content.splitlines()[0].startswith("4: ")
    assert "continue with offset=6" in content


def test_read_file_escape_is_error_not_exception(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "read_file", path="../outside.txt")
    assert is_error
    assert "outside the workspace" in content


def test_read_file_offset_past_end_is_error(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "read_file", path="app/pricing.py", offset=9999)
    assert is_error
    assert "past the end" in content


def test_invalid_arguments_are_correctable_error(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "read_file", path="app/pricing.py", offset=-1)
    assert is_error
    assert "invalid arguments" in content


def test_unknown_tool_is_error(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "write_file", path="x", content="y")
    assert is_error
    assert "unknown tool" in content


def test_glob_lists_matching_files(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "glob", pattern="app/*.py")
    assert not is_error
    assert content == "app/pricing.py"


def test_list_dir_marks_directories(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "list_dir", path=".")
    assert not is_error
    entries = content.splitlines()
    assert "app/" in entries
    assert ".git" not in entries  # VCS internals hidden


def test_find_symbol_locates_definition_with_span(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "find_symbol", name="average_item_price")
    assert not is_error
    assert content.startswith("app/pricing.py:4-6:")
    assert "def average_item_price" in content


def test_find_symbol_missing_name_reports_no_definition(tmp_path):
    content, is_error = _run(_toolbox(tmp_path), "find_symbol", name="does_not_exist")
    assert not is_error
    assert "no definition" in content
