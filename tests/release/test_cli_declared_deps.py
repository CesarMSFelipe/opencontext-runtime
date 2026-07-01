"""The CLI package must declare every first-party package it imports.

Guards against user-facing ModuleNotFoundError: tests pass via PYTHONPATH,
but a real install only gets declared dependencies.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

CLI_PYPROJECT = (
    Path(__file__).resolve().parents[2] / "packages" / "opencontext_cli" / "pyproject.toml"
)


def test_cli_declares_imported_first_party_packages() -> None:
    deps = tomllib.loads(CLI_PYPROJECT.read_text())["project"]["dependencies"]
    names = {d.split(">=")[0].split("==")[0].strip().lower() for d in deps}
    for required in (
        "opencontext-core",
        "opencontext-profiles",
        "opencontext-memory",
        "opencontext-sdd",
    ):
        assert required in names, (
            f"opencontext_cli imports {required.replace('-', '_')} but does not declare it"
        )
