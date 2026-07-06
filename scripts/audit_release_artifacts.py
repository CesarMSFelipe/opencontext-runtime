#!/usr/bin/env python3
"""Release artifact hygiene audit (RELEASE_CONTRACT.md, AC-029).

Unpacks the entry list of built release artifacts (wheel / sdist / pyz / zip)
and fails when any forbidden local-state entry ships inside: .git, venvs,
tool caches, __pycache__, .opencontext/.storage state, coverage data, or
log files. Sdists may carry their own build-generated ``<pkg>.egg-info/`` at
the archive root; any other egg-info is a stray leak.

Usage:
    python scripts/audit_release_artifacts.py [artifact ...]

Without arguments it audits every artifact under ``dist/`` and
``packages/*/dist/``. Exit codes: 0 clean, 1 offenders found, 2 no artifact.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directory / file segments that must never appear inside a published artifact.
_FORBIDDEN_SEGMENTS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".ci-venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".opencontext",
        ".storage",
        "logs",
    }
)

_ZIP_SUFFIXES = (".whl", ".pyz", ".zip")
_SDIST_SUFFIXES = (".tar.gz", ".tgz")


def _segment_is_forbidden(segment: str) -> bool:
    if segment in _FORBIDDEN_SEGMENTS:
        return True
    if segment == ".coverage" or segment.startswith(".coverage."):
        return True
    return segment.endswith(".log")


def find_offenders(entries: Iterable[str], *, allow_root_egg_info: bool = False) -> list[str]:
    """Return entries violating the RELEASE_CONTRACT forbidden-content rules.

    ``allow_root_egg_info`` permits the build-generated ``<pkg>.egg-info/``
    directly under an sdist's root directory (segment index 1).
    """
    offenders: list[str] = []
    for entry in entries:
        segments = [s for s in entry.split("/") if s]
        for index, segment in enumerate(segments):
            if _segment_is_forbidden(segment):
                offenders.append(entry)
                break
            if segment.endswith(".egg-info"):
                if allow_root_egg_info and index == 1:
                    continue
                offenders.append(entry)
                break
    return offenders


def _entries(artifact: Path) -> list[str]:
    if artifact.name.endswith(_SDIST_SUFFIXES):
        with tarfile.open(artifact) as tf:
            return tf.getnames()
    if artifact.suffix in _ZIP_SUFFIXES:
        with zipfile.ZipFile(artifact) as zf:
            return zf.namelist()
    raise ValueError(f"unsupported release artifact format: {artifact.name}")


def audit_artifact(artifact: Path) -> list[str]:
    """Audit one built artifact; return its offending entries."""
    is_sdist = artifact.name.endswith(_SDIST_SUFFIXES)
    return find_offenders(_entries(artifact), allow_root_egg_info=is_sdist)


def _discover_artifacts() -> list[Path]:
    patterns = ("*.whl", "*.tar.gz", "*.pyz")
    found: list[Path] = []
    for dist_dir in (ROOT / "dist", *sorted((ROOT / "packages").glob("*/dist"))):
        for pattern in patterns:
            found.extend(sorted(dist_dir.glob(pattern)))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "artifacts",
        nargs="*",
        type=Path,
        help="Artifacts to audit (default: dist/ and packages/*/dist/).",
    )
    args = parser.parse_args(argv)

    artifacts = [p for p in args.artifacts if p.is_file()] if args.artifacts else []
    missing = [p for p in args.artifacts if not p.is_file()]
    if not args.artifacts:
        artifacts = _discover_artifacts()
    for path in missing:
        print(f"MISSING {path}", file=sys.stderr)
    if not artifacts:
        print("no release artifacts found to audit", file=sys.stderr)
        return 2

    failed = False
    for artifact in artifacts:
        offenders = audit_artifact(artifact)
        if offenders:
            failed = True
            print(f"FAIL {artifact} — {len(offenders)} forbidden entries:")
            for entry in offenders:
                print(f"  {entry}")
        else:
            print(f"OK   {artifact}")
    if missing:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
