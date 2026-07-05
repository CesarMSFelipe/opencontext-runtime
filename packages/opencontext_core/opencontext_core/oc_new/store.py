"""File-backed store for OcNewRunState objects."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.oc_new.models import OcNewRunState
from opencontext_core.paths import StorageMode, resolve_workspace_path


class OcNewStore:
    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)

    def run_dir(self, run_id: str) -> Path:
        return resolve_workspace_path(self.root, StorageMode.local) / "runs" / run_id

    def state_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "state.json"

    def save(self, state: OcNewRunState) -> Path:
        path = self.state_path(state.identity.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, run_id: str) -> OcNewRunState:
        path = self.state_path(run_id)
        if not path.exists():
            raise FileNotFoundError(f"oc-new state not found: {run_id}")
        return OcNewRunState.model_validate_json(path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[OcNewRunState]:
        runs_dir = resolve_workspace_path(self.root, StorageMode.local) / "runs"
        if not runs_dir.exists():
            return []
        states: list[OcNewRunState] = []
        for state_file in sorted(runs_dir.glob("*/state.json"), key=lambda p: p.stat().st_mtime):
            try:
                states.append(
                    OcNewRunState.model_validate_json(state_file.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
        return states

    def latest(self) -> OcNewRunState | None:
        runs = self.list_runs()
        return runs[-1] if runs else None
