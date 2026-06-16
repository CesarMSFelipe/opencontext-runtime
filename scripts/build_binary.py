#!/usr/bin/env python3
"""Build a single-file executable for the OpenContext CLI using stdlib zipapp.

Produces ``dist/opencontext.pyz`` — one file you can copy anywhere and run with
``python3 opencontext.pyz`` (or directly on Unix via its shebang). It bundles the
OpenContext source; third-party dependencies resolve from the Python environment,
so it is a portable single-file app rather than a fully static binary. For a
dependency-free static binary, build with PyInstaller (see README).

Usage:
    python3 scripts/build_binary.py [--output dist/opencontext.pyz]
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Packages bundled into the archive (import name -> source directory).
_PACKAGES = {
    "opencontext_core": ROOT / "packages" / "opencontext_core" / "opencontext_core",
    "opencontext_cli": ROOT / "packages" / "opencontext_cli" / "opencontext_cli",
}
_MAIN = "from opencontext_cli.main import main\n\nif __name__ == '__main__':\n    main()\n"


def build(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        for name, src in _PACKAGES.items():
            if not src.is_dir():
                raise SystemExit(f"source package not found: {src}")
            shutil.copytree(
                src,
                staging / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"),
            )
        (staging / "__main__.py").write_text(_MAIN, encoding="utf-8")
        zipapp.create_archive(
            staging,
            target=output,
            interpreter="/usr/bin/env python3",
            compressed=True,
        )
    output.chmod(0o755)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "opencontext.pyz",
        help="Output path for the .pyz archive.",
    )
    args = parser.parse_args()
    out = build(args.output)
    size_kb = out.stat().st_size / 1024
    print(f"Built {out} ({size_kb:.0f} KB)")
    print("Run it with:  python3", out)


if __name__ == "__main__":
    main()
