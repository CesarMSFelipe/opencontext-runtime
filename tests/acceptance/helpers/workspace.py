"""Isolated workspace + environment factory for black-box acceptance tests.

Each test workspace gets:

* its own project root (optionally seeded from ``tests/acceptance/fixtures/``);
* its own throwaway ``$HOME`` and XDG dirs, so no global state ever leaks in or
  out (this repo's daemon otherwise pollutes the developer's ``~/.opencontext``);
* an environment stripped of every ``OPENCONTEXT_*`` variable and of Python
  path leakage (``PYTHONPATH``/``VIRTUAL_ENV``), so the resolved ``--oc-bin``
  binary runs exactly as an end user's install would.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

#: The deterministic ApplyEdit set that fixes the seeded ``add`` bug
#: (mirrors tests/golden/oc_flow_bugfix_python/provider_stub.json mechanics).
CORRECT_ADD_EDITS = [
    {
        "path": "app.py",
        "operation": "replace_range",
        "start_line": 5,
        "end_line": 5,
        "content": "    return a + b",
        "reason": "fix off-by-operator: add() must return the sum of its arguments",
        "requirement_refs": ["add returns the sum of its arguments"],
    }
]

#: A deliberately wrong ApplyEdit set (multiplies instead of adding).
WRONG_ADD_EDITS = [
    {
        "path": "app.py",
        "operation": "replace_range",
        "start_line": 5,
        "end_line": 5,
        "content": "    return a * b",
        "reason": "intentionally wrong fix for the failed-verification scenario",
        "requirement_refs": ["add returns the sum of its arguments"],
    }
]

#: Config that drives the REAL `opencontext run` mutation path credential-free
#: via the deterministic `test_stub` provider (see providers/test_stub.py).
TEST_STUB_CONFIG = """\
runtime:
  oc_flow_enabled: true
  gateway_enabled: true
  durable_artifacts: true
provider: test_stub
edits_file: provider_stub.json
"""


@dataclass
class Workspace:
    """A fully isolated project root + subprocess environment."""

    root: Path
    home: Path
    env: dict[str, str]

    def write_stub_provider(self, edits: list[dict[str, object]]) -> None:
        """Install the test_stub executor config + its ApplyEdit file."""
        (self.root / "provider_stub.json").write_text(json.dumps(edits, indent=2), encoding="utf-8")
        (self.root / "opencontext.yaml").write_text(TEST_STUB_CONFIG, encoding="utf-8")

    def set_tdd_mode(self, mode: str) -> None:
        """Flip ``workflow_defaults.tdd_mode`` in the installed harness.yaml."""
        harness = self.root / ".opencontext" / "harness.yaml"
        text = harness.read_text(encoding="utf-8")
        assert "tdd_mode:" in text, f"no tdd_mode key in {harness}"
        import re

        harness.write_text(re.sub(r"tdd_mode: \S+", f"tdd_mode: {mode}", text), encoding="utf-8")


def build_isolated_env(home: Path) -> dict[str, str]:
    """A subprocess env with tmp HOME/XDG dirs and no OpenContext/Python leakage."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("OPENCONTEXT_")
        and key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTEST_CURRENT_TEST"}
    }
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_STATE_HOME"] = str(home / ".local" / "state")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["NO_COLOR"] = "1"
    env["COLUMNS"] = "200"
    return env


def make_workspace(base_dir: Path, fixture: str | None = None) -> Workspace:
    """Create an isolated workspace under *base_dir*, optionally from a fixture."""
    root = base_dir / "repo"
    home = base_dir / "home"
    if fixture is not None:
        source = FIXTURES_DIR / fixture
        assert source.is_dir(), f"unknown acceptance fixture: {fixture}"
        shutil.copytree(source, root)
    else:
        root.mkdir(parents=True, exist_ok=True)
    return Workspace(root=root, home=home, env=build_isolated_env(home))
