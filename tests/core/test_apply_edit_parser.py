"""T6: parse_file_edits ApplyEdit detection; _collect_edits materializer.

Tests:
  T6-1: parse_file_edits returns ApplyEdit objects when 'operation' key present
  T6-2: parse_file_edits still returns legacy dicts for {path, content} elements
  T6-3: _collect_edits materializes ApplyEdit→FileEdit via in-memory apply_edit()
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation, parse_file_edits


class TestParseFileEditsApplyEditArray:
    """T6-1: elements with 'operation' key are parsed as ApplyEdit objects."""

    def test_parse_file_edits_applyedit_array(self) -> None:
        payload = json.dumps(
            [
                {
                    "path": "src/foo.py",
                    "operation": "replace_range",
                    "start_line": 1,
                    "end_line": 3,
                    "content": "# replaced",
                }
            ]
        )
        result = parse_file_edits(payload)
        assert len(result) == 1
        assert isinstance(result[0], ApplyEdit), f"Expected ApplyEdit, got {type(result[0])}"
        edit = result[0]
        assert edit.path == "src/foo.py"
        assert edit.operation == ApplyOperation.REPLACE_RANGE
        assert edit.start_line == 1
        assert edit.end_line == 3

    def test_parse_file_edits_invalid_applyedit_dropped(self) -> None:
        """An 'operation' element that fails ApplyEdit validation should be dropped."""
        payload = json.dumps(
            [
                {
                    "path": "src/foo.py",
                    "operation": "replace_range",
                    # missing start_line, end_line — pydantic will reject extra=forbid
                    "unknown_field": "bad",
                }
            ]
        )
        result = parse_file_edits(payload)
        # Must be dropped on ValidationError (additive: no crash)
        assert result == []


class TestParseFileEditsLegacyArray:
    """T6-2: legacy {path, content} elements still return dicts."""

    def test_parse_file_edits_legacy_array(self) -> None:
        payload = json.dumps([{"path": "src/bar.py", "content": "print('hello')\n"}])
        result = parse_file_edits(payload)
        assert len(result) == 1
        item = result[0]
        assert isinstance(item, dict), f"Expected dict, got {type(item)}"
        assert item["path"] == "src/bar.py"
        assert item["content"] == "print('hello')\n"

    def test_parse_file_edits_mixed_array(self) -> None:
        """Mixed array: ApplyEdit + legacy both appear in output."""
        payload = json.dumps(
            [
                {
                    "path": "src/foo.py",
                    "operation": "replace_range",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "# new line 1",
                },
                {"path": "src/bar.py", "content": "# whole file"},
            ]
        )
        result = parse_file_edits(payload)
        assert len(result) == 2
        assert isinstance(result[0], ApplyEdit)
        assert isinstance(result[1], dict)


def test_apply_instruction_names_applyedit_as_primary_protocol() -> None:
    from opencontext_core.agents.executor import _APPLY_INSTRUCTION

    assert "primary shape is ApplyEdit" in _APPLY_INSTRUCTION
    assert "Legacy whole-file" in _APPLY_INSTRUCTION
    assert '"operation"' in _APPLY_INSTRUCTION


class TestCollectEdits:
    """T6-3: ApplyPhase._collect_edits materializes ApplyEdit→FileEdit."""

    def test_collect_edits_materializes_applyedit_replace_range(self) -> None:
        from opencontext_core.harness.phases import ApplyPhase

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create a target file with known content
            target = root / "src" / "hello.py"
            target.parent.mkdir(parents=True)
            target.write_text("line1\nline2\nline3\n", encoding="utf-8")

            edit = ApplyEdit(
                path="src/hello.py",
                operation=ApplyOperation.REPLACE_RANGE,
                start_line=2,
                end_line=2,
                content="# replaced line 2",
            )

            class FakeState:
                from typing import ClassVar

                apply_edits: ClassVar[list] = [edit]
                root = Path(tmp)

            edits = ApplyPhase._collect_edits(FakeState())
            assert len(edits) == 1
            from opencontext_core.harness.phases import FileEdit

            assert isinstance(edits[0], FileEdit)
            assert edits[0].path == "src/hello.py"
            # The materialized content should have line 2 replaced
            assert "# replaced line 2" in edits[0].content
            assert "line1" in edits[0].content
            assert "line3" in edits[0].content
            # line2 should be gone
            assert "line2" not in edits[0].content
