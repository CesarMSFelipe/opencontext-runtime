"""E2E developer-journey bootstrap (B10 / AVH-017).

Copies the DoD golden fixture (``tests/golden/oc_flow_bugfix_python``) to an isolated
temp project with a temp ``$HOME``, so the journey drives the real CLI
(``install -> doctor --strict -> index``) without touching the developer's machine or
global config.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from opencontext_core.evaluation.golden import FIXTURE_DIRS, GOLDEN_ROOT


@pytest.fixture
def golden_root() -> Path:
    """The source-controlled DoD bugfix fixture directory."""
    return GOLDEN_ROOT / FIXTURE_DIRS["oc-flow-localized-bugfix"]


@pytest.fixture
def isolated_env(golden_root: Path, tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """An isolated copy of the golden project + an env with a temp ``$HOME``."""
    work = tmp_path / "repo"
    shutil.copytree(golden_root, work)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    return work, env
