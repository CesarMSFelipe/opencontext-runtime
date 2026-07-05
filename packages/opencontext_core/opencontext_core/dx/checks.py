"""Local check registry."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.paths import StorageMode, resolve_workspace_path

CHECK_NAMES = ["security", "quality", "docs", "performance", "dependencies"]


def ensure_checks(root: Path) -> list[Path]:
    """Ensure local checks exist and return their paths."""

    checks_dir = resolve_workspace_path(root, StorageMode.local) / "checks"
    checks_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name in CHECK_NAMES:
        path = checks_dir / f"{name}.yaml"
        if not path.exists():
            path.write_text(f"# {name} check\nenabled: true\n", encoding="utf-8")
        paths.append(path)
    return paths
