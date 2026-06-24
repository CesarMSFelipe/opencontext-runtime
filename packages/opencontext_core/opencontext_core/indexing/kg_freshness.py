"""KGFreshnessChecker — detect stale KG index relative to source files.

Reads ``project_manifest.json`` (the canonical project index produced by
``opencontext_core.indexing.project_indexer``) and compares the most recent
source-file mtime against the index timestamp. When the index timestamp is
missing the oldest file mtime is used as the baseline — degraded mode that
preserves the "always answer, never fabricate" contract.

The git-mtime path uses ``git log -1 --format=%ct`` when available and falls
back to the manifest's own ``modified_at_epoch`` value, so the check works
on plain tmp fixtures (no git repo required) and on real checked-out trees.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FreshnessReport:
    """Outcome of a freshness check."""

    fresh: bool
    stalest_path: str | None
    stalest_age_s: float | None


class KGFreshnessChecker:
    """Stateless checker — pass project root + manifest path each call."""

    @staticmethod
    def check(project_root: Path, manifest_path: Path) -> FreshnessReport:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        files: list[dict[str, object]] = manifest.get("files") or []
        if not files:
            return FreshnessReport(fresh=True, stalest_path=None, stalest_age_s=None)

        index_ts = manifest.get("index_timestamp")
        baseline = index_ts if isinstance(index_ts, (int, float)) else _oldest(files)

        stalest_path: str | None = None
        stalest_mtime = baseline
        for entry in files:
            mtime = _resolve_mtime(project_root, entry)
            if mtime > stalest_mtime:
                stalest_mtime = mtime
                stalest_path = entry.get("path")

        if stalest_path is None:
            return FreshnessReport(fresh=True, stalest_path=None, stalest_age_s=None)
        return FreshnessReport(
            fresh=False,
            stalest_path=stalest_path,
            stalest_age_s=max(0.0, stalest_mtime - baseline),
        )


def _oldest(files: list[dict[str, object]]) -> float:
    mtimes = [_resolve_mtime(None, f) for f in files]
    return min(mtimes) if mtimes else 0.0


def _resolve_mtime(project_root: Path | None, entry: dict) -> float:
    """Resolve a single file's mtime.

    Tries git first (when ``project_root`` is a git repo), then the manifest's
    ``metadata.modified_at_epoch``, then filesystem mtime as a final fallback.
    """
    rel = entry.get("path", "")
    meta = entry.get("metadata") or {}
    if "modified_at_epoch" in meta:
        try:
            return float(meta["modified_at_epoch"])
        except (TypeError, ValueError):
            pass
    if project_root is not None:
        git_ts = _git_mtime(project_root, rel)
        if git_ts is not None:
            return git_ts
        fs_path = project_root / rel
        try:
            return float(fs_path.stat().st_mtime)
        except OSError:
            pass
    return 0.0


def _git_mtime(project_root: Path, rel_path: str) -> float | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, "-C", str(project_root), "log", "-1", "--format=%ct", "--", rel_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return float(result.stdout.strip().splitlines()[-1])
    except ValueError:
        return None


if __name__ == "__main__":
    # Self-check: fresh and stale scenarios on a tmp manifest.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest = root / "project_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "files": [
                        {"path": "a.py", "metadata": {"modified_at_epoch": 100.0}},
                        {"path": "b.py", "metadata": {"modified_at_epoch": 500.0}},
                    ],
                    "index_timestamp": 1000.0,
                }
            ),
            encoding="utf-8",
        )
        rep = KGFreshnessChecker.check(root, manifest)
        assert rep.fresh is True, rep
        # Now mark b.py as modified after the index.
        manifest.write_text(
            json.dumps(
                {
                    "files": [
                        {"path": "a.py", "metadata": {"modified_at_epoch": 100.0}},
                        {"path": "b.py", "metadata": {"modified_at_epoch": 9_999.0}},
                    ],
                    "index_timestamp": 1000.0,
                }
            ),
            encoding="utf-8",
        )
        rep2 = KGFreshnessChecker.check(root, manifest)
        assert rep2.fresh is False, rep2
        assert rep2.stalest_path == "b.py", rep2
        print("indexing/kg_freshness.py self-check passed.")