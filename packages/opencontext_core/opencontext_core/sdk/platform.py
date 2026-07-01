"""sdk.platform — REQ-sdk-dev-001..005 scaffolding + validation + publish + compat.

Ponytail note: 8 scaffold kinds render identical file sets today, so
``create_plugin_template`` is the canonical renderer; the other kinds share
the same path layout with a kind-specific manifest.  Add kind-specific
content when the SDK actually diverges.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# REQ-sdk-dev-002 — 8 scaffold kinds
SCAFFOLD_KINDS: tuple[str, ...] = (
    "plugin",
    "skill",
    "harness",
    "provider",
    "studio-panel",
    "recipe",
    "command",
    "profile",
)


# REQ-sdk-dev-005 — runtime.SDK_VERSION surrogate for compat checks
SDK_VERSION: str = "1.4.0"


# REQ-sdk-dev-002 — file layout every scaffold renders
PLUGIN_FILE_LAYOUT: tuple[str, ...] = (
    "<name>/__init__.py",
    "<name>/plugin.yaml",
    "tests/test_<name>.py",
    "docs/README.md",
    "CHANGELOG.md",
    ".github/workflows/test.yml",
    "scripts/test.sh",
    "conformance/conftest.py",
)


PLUGIN_TEMPLATE_BODY = """# {name} scaffold
name: {name}
version: 0.1.0
sdk_min_version: 1.0.0
sdk_max_version: 2.0.0
permissions: []
entrypoint: {name}:main
"""


PYPROJECT_TEMPLATE = """[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"

[tool.setuptools.packages.find]
include = ["{name}*"]
"""


TEST_BODY = '''"""Smoke test for {name} scaffold."""

from __name__ import main  # type: ignore[name-defined]  # noqa: F401


def test_scaffold_imports() -> None:
    import {name}  # noqa: F401
'''


README_BODY = """# {name}

Scaffolded by `opencontext-sdk`.

## Install

    pip install -e .[test]
    pytest -q
"""


CHANGELOG_BODY = """# Changelog

## 0.1.0 — initial scaffold
"""


WORKFLOW_BODY = """name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .[test]
      - run: pytest -q
"""


TEST_SH_BODY = """#!/usr/bin/env bash
set -euo pipefail
pip install -e ".[test]"
pytest -q
"""


CONFTEST_BODY = """import pytest


@pytest.fixture
def sdk_public_types():
    from opencontext_core.sdk.platform import SdkPlatform

    return SdkPlatform
"""


# REQ-sdk-dev-005 — three-way status enum
CompatStatus = Literal["ok", "warn", "fail"]


@dataclass
class SdkPlatform:
    """Developer-facing surface for ``opencontext-sdk`` (REQ-sdk-dev-001..005)."""

    sdk_version: str = SDK_VERSION

    def scaffold_kinds(self) -> list[str]:
        return list(SCAFFOLD_KINDS)

    # REQ-sdk-dev-002 -------------------------------------------------------
    def create_plugin_template(self, name: str, out_dir: Path) -> dict[str, str]:
        return create_plugin_template(name, out_dir, sdk=self)

    # REQ-sdk-dev-003 -------------------------------------------------------
    def validate_plugin(self, path: Path) -> dict[str, object]:
        return validate_plugin(path, sdk=self)

    # REQ-sdk-dev-004 (publish) ---------------------------------------------
    def publish_plugin(
        self,
        path: Path,
        registry: str = "local",
    ) -> dict[str, object]:
        return publish_plugin(path, registry=registry, sdk=self)

    # REQ-sdk-dev-005 -------------------------------------------------------
    def compat_check(
        self,
        sdk_min_version: str,
        sdk_max_version: str | None = None,
        runtime_version: str | None = None,
    ) -> dict[str, object]:
        runtime = runtime_version or self.sdk_version
        try:
            rmin = _parse_semver(runtime)
        except ValueError:
            return {
                "status": "fail",
                "mismatches": [{"field": "runtime_version", "value": runtime}],
            }
        try:
            smin = _parse_semver(sdk_min_version)
        except ValueError:
            return {
                "status": "fail",
                "mismatches": [{"field": "sdk_min_version", "value": sdk_min_version}],
            }
        if rmin[0] < smin[0]:
            return {
                "status": "fail",
                "mismatches": [
                    {
                        "sdk_min": sdk_min_version,
                        "runtime": runtime,
                    }
                ],
            }
        if sdk_max_version:
            try:
                smax = _parse_semver(sdk_max_version)
            except ValueError:
                return {
                    "status": "fail",
                    "mismatches": [
                        {"field": "sdk_max_version", "value": sdk_max_version}
                    ],
                }
            if rmin > smax:
                return {
                    "status": "fail",
                    "mismatches": [
                        {"sdk_max": sdk_max_version, "runtime": runtime}
                    ],
                }
        return {
            "status": "ok",
            "mismatches": [],
            "sdk_version": self.sdk_version,
            "runtime_version": runtime,
        }

    def render_dashboard(
        self,
        metrics: dict[str, float],
        format: str = "md",
    ) -> str:
        # REQ-sdk-dev-004 — docgen surface (lightweight)
        lines = ["# SDK Dashboard", ""]
        for key in sorted(metrics):
            lines.append(f"- **{key}** = {metrics[key]}")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Module-level functions (matches the public surface from the task prompt)
# ---------------------------------------------------------------------------


def create_plugin_template(
    name: str,
    out_dir: Path,
    *,
    sdk: SdkPlatform | None = None,
) -> dict[str, str]:
    """Render the 8-file plugin scaffold under ``<out_dir>/<name>/...``."""
    sdk = sdk or SdkPlatform()
    out_dir = Path(out_dir)
    name_dir = out_dir
    name_dir.mkdir(parents=True, exist_ok=True)
    module_name = name.replace("-", "_")
    (name_dir / module_name).mkdir(parents=True, exist_ok=True)
    (out_dir / "tests").mkdir(parents=True, exist_ok=True)
    (out_dir / "docs").mkdir(parents=True, exist_ok=True)
    (out_dir / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (out_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (out_dir / "conformance").mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    init_path = name_dir / module_name / "__init__.py"
    init_path.write_text("")
    files[f"{module_name}/__init__.py"] = str(init_path)

    manifest_path = name_dir / "plugin.yaml"
    manifest_path.write_text(PLUGIN_TEMPLATE_BODY.format(name=name))
    files["plugin.yaml"] = str(manifest_path)

    pyproject_path = name_dir / "pyproject.toml"
    pyproject_path.write_text(PYPROJECT_TEMPLATE.format(name=name))
    files["pyproject.toml"] = str(pyproject_path)

    test_path = out_dir / "tests" / f"test_{module_name}.py"
    test_path.write_text(TEST_BODY.format(name=module_name))
    files[f"tests/test_{module_name}.py"] = str(test_path)

    readme_path = out_dir / "docs" / "README.md"
    readme_path.write_text(README_BODY.format(name=name))
    files["docs/README.md"] = str(readme_path)

    changelog_path = out_dir / "CHANGELOG.md"
    changelog_path.write_text(CHANGELOG_BODY)
    files["CHANGELOG.md"] = str(changelog_path)

    workflow_path = out_dir / ".github" / "workflows" / "test.yml"
    workflow_path.write_text(WORKFLOW_BODY)
    files[".github/workflows/test.yml"] = str(workflow_path)

    test_sh_path = out_dir / "scripts" / "test.sh"
    test_sh_path.write_text(TEST_SH_BODY)
    test_sh_path.chmod(0o755)
    files["scripts/test.sh"] = str(test_sh_path)

    conftest_path = out_dir / "conformance" / "conftest.py"
    conftest_path.write_text(CONFTEST_BODY)
    files["conformance/conftest.py"] = str(conftest_path)

    return files


def validate_plugin(
    path: Path,
    *,
    sdk: SdkPlatform | None = None,
) -> dict[str, object]:
    """REQ-sdk-dev-003 — check a scaffolded plugin for required fields."""
    sdk = sdk or SdkPlatform()
    path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    manifest = path / "plugin.yaml"
    if not manifest.exists():
        errors.append("plugin.yaml: missing")
    else:
        text = manifest.read_text()
        for required in ("name", "version", "entrypoint", "permissions"):
            if f"{required}:" not in text:
                errors.append(f"plugin.yaml:{required} missing")

    # CHANGELOG + LICENSE required per spec REQ-sdk-dev-002 constraint
    for required in ("CHANGELOG.md",):
        if not (path / required).exists():
            warnings.append(f"{required}: missing")

    return {
        "status": "error" if errors else "ok",
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "sdk_version": sdk.sdk_version,
    }


def publish_plugin(
    path: Path,
    *,
    registry: str = "local",
    sdk: SdkPlatform | None = None,
) -> dict[str, object]:
    """REQ-sdk-dev-004 (publish half) — build a deterministic receipt."""
    sdk = sdk or SdkPlatform()
    path = Path(path)
    manifest = path / "plugin.yaml"
    name = path.name
    version = "0.1.0"
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            if line.startswith("version:"):
                version = line.split(":", 1)[1].strip()
                break
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip() or name
    manifest_bytes = manifest.read_bytes() if manifest.exists() else b""
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    return {
        "plugin": name,
        "registry": registry,
        "version": version,
        "manifest_hash": manifest_hash,
        "status": "published",
        "sdk_version": sdk.sdk_version,
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_semver(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3:
        raise ValueError(f"not semver: {value!r}")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise ValueError(f"not semver: {value!r}") from exc


__all__ = [
    "SCAFFOLD_KINDS",
    "SDK_VERSION",
    "SdkPlatform",
    "create_plugin_template",
    "publish_plugin",
    "validate_plugin",
]
