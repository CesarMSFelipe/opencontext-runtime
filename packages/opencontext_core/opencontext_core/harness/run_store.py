"""RunStore — file-backed index of run artifact directories."""

from __future__ import annotations

from pathlib import Path


class RunStore:
    """Maps run IDs to artifact directory paths via a JSON index."""

    def __init__(self, root: Path | str = ".") -> None:
        self.runs_path = Path(root) / ".opencontext" / "runs"
        self.runs_path.mkdir(parents=True, exist_ok=True)

    def _index_path(self) -> Path:
        return self.runs_path / "index.json"

    def _read(self) -> dict[str, str]:
        p = self._index_path()
        if not p.exists():
            return {}
        import json

        data: dict[str, str] = json.loads(p.read_text(encoding="utf-8"))
        return data

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
