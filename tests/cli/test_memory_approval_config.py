"""`memory.approval_required` config seam → v2 saves land proposed.

MEM-002: pending memory requires approval before use. The CLI save path reads
``memory.approval_required`` from the project config through
``_approval_required``; this pins the seam so a silent config-resolution
regression (attr rename, load failure) cannot flip approval-gated saves back
to ``active`` without a test failing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from opencontext_memory import MemoryStore
from opencontext_memory.tools.mem_get_observation import mem_get_observation

from opencontext_cli.commands.memory_v2_cmd import _approval_required, _dispatch_tool


def _save_args(content: str = "pending insight about the deploy flow") -> argparse.Namespace:
    return argparse.Namespace(
        title="Pending note",
        content=content,
        type="manual",
        scope="project",
        topic_key=None,
        no_capture_prompt=True,
    )


def _saved_row(cwd: Path, capsys: Any) -> dict[str, Any]:
    _dispatch_tool("save", cwd, _save_args())
    receipt = json.loads(capsys.readouterr().out)
    store = MemoryStore.open(cwd / ".storage" / "opencontext" / "memory_v2.db")
    return mem_get_observation(store, observation_id=receipt["receipt"]["id"])


def test_config_approval_required_true_resolves(tmp_path: Path) -> None:
    """MEM-002: `memory.approval_required: true` in opencontext.yaml resolves True."""
    (tmp_path / "opencontext.yaml").write_text(
        "memory:\n  approval_required: true\n", encoding="utf-8"
    )
    assert _approval_required(tmp_path) is True


def test_config_default_resolves_false(tmp_path: Path) -> None:
    """MEM-002: without a project config the approval gate defaults to False."""
    assert _approval_required(tmp_path) is False


def test_cli_save_lands_proposed_under_approval_required(tmp_path: Path, capsys: Any) -> None:
    """MEM-002: with approval_required true, a CLI v2 save lands 'proposed'."""
    (tmp_path / "opencontext.yaml").write_text(
        "memory:\n  approval_required: true\n", encoding="utf-8"
    )
    row = _saved_row(tmp_path, capsys)
    assert row["lifecycle_state"] == "proposed"


def test_cli_save_lands_active_without_approval_config(tmp_path: Path, capsys: Any) -> None:
    """MEM-002: without the approval gate a CLI v2 save stays 'active'."""
    row = _saved_row(tmp_path, capsys)
    assert row["lifecycle_state"] == "active"
