"""RunStore — file-backed index of run artifact directories."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.paths import execution_state


class RunStore:
    """Maps run IDs to artifact directory paths via a JSON index."""

    def __init__(self, root: Path | str = ".") -> None:
        self.runs_path = execution_state.runs_root(root)
        self.runs_path.mkdir(parents=True, exist_ok=True)
        self._read_roots = execution_state.execution_read_roots(root, "runs")

    def _index_path(self) -> Path:
        return self.runs_path / "index.json"

    def _read(self) -> dict[str, str]:
        import json

        # Active index first; fall back to a legacy in-repo index so runs
        # persisted before the user-mode migration stay listable.
        for candidate in self._read_roots:
            p = candidate / "index.json"
            if not p.exists():
                continue
            data: dict[str, str] = json.loads(p.read_text(encoding="utf-8"))
            return data
        return {}

    def _write(self, index: dict[str, str]) -> None:
        import json

        tmp = self._index_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
        tmp.replace(self._index_path())

    def list_run_ids(self) -> list[str]:
        return list(self._read().keys())

    def run_dir(self, run_id: str) -> Path:
        return self.runs_path / run_id

    def exists(self, run_id: str) -> bool:
        return run_id in self._read()

    def artifact_path(self, run_id: str, name: str) -> Path:
        index = self._read()
        if run_id not in index:
            raise KeyError(run_id)
        return Path(index[run_id]) / name

    def register(self, run_id: str, artifact_dir: Path) -> None:
        index = self._read()
        index[run_id] = str(artifact_dir)
        self._write(index)

    def passed_phase_artifacts(self, run_id: str, completed_phases: set[str]) -> list[Path]:
        """Return on-disk artifact files produced by ``completed_phases`` of a run.

        Reads the run's ``artifacts.json`` ledger and returns the existing files
        whose producing ``phase`` is in ``completed_phases`` — the set a resumed
        run rehydrates so a downstream phase finds its inputs (spec PR-004 REQ-10).
        Absolute artifact paths are honoured; relative ones resolve under the run
        dir. Missing ledger / files are skipped. Never raises.
        """
        import json

        run_dir = self.run_dir(run_id)
        artifacts_json = run_dir / "artifacts.json"
        out: list[Path] = []
        if not artifacts_json.exists():
            return out
        try:
            data = json.loads(artifacts_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return out
        seen: set[str] = set()
        for entry in data.get("artifacts", []) if isinstance(data, dict) else []:
            if not isinstance(entry, dict):
                continue
            if entry.get("phase") not in completed_phases:
                continue
            raw = str(entry.get("path") or "")
            if not raw:
                continue
            path = Path(raw)
            if not path.is_absolute():
                path = run_dir / path
            key = str(path)
            if key in seen or not path.exists() or not path.is_file():
                continue
            seen.add(key)
            out.append(path)
        return out
