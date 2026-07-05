"""Runtime state shown beside the terminal logo."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from opencontext_core.config_resolver import resolve_active_storage_file


@dataclass(frozen=True)
class RuntimeBrandState:
    project_name: str
    project_status: str
    files: int = 0
    symbols: int = 0
    kg_status: str = "not indexed"
    memory_backend: str = "local"
    flow_mode: str = "unknown"
    run_label: str = "no active run"
    phase_label: str = "-"
    next_label: str = "opencontext install"


def gather_runtime_brand_state(root: str | Path = ".") -> RuntimeBrandState:
    """Best-effort project/run status for CLI/TUI chrome."""
    base = Path(root).resolve()
    project_name = base.name
    project_status = "installed" if (base / "opencontext.yaml").exists() else "not installed"
    files, symbols, kg_status = _kg_status(base)
    memory_backend, flow_mode = _config_status(base)
    run_label, phase_label, next_label = _run_status(base)
    if project_status == "not installed" and next_label == "no active run":
        next_label = "opencontext install"
    return RuntimeBrandState(
        project_name=project_name,
        project_status=project_status,
        files=files,
        symbols=symbols,
        kg_status=kg_status,
        memory_backend=memory_backend,
        flow_mode=flow_mode,
        run_label=run_label,
        phase_label=phase_label,
        next_label=next_label,
    )


def _kg_status(base: Path) -> tuple[int, int, str]:
    # Resolve through the active storage mode (same resolver the indexer uses),
    # with an honest legacy in-repo fallback for unmigrated projects.
    db = resolve_active_storage_file(base, "context_graph.db")
    if not db.exists():
        return 0, 0, "not indexed"
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT kind, COUNT(*) AS n FROM nodes GROUP BY kind").fetchall()
            try:
                files_row = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()
            except sqlite3.Error:
                files_row = None
        finally:
            conn.close()
        counts = {str(r["kind"]): int(r["n"]) for r in rows}
        files = int(files_row["n"]) if files_row is not None else counts.get("file", 0)
        symbols = sum(counts.get(k, 0) for k in ("function", "method", "class", "symbol"))
        total = sum(counts.values())
        return files, symbols, f"healthy ({total} nodes)"
    except Exception:
        return 0, 0, "unreadable"


def _config_status(base: Path) -> tuple[str, str]:
    try:
        from opencontext_core.config import load_config

        cfg_path = base / "opencontext.yaml"
        if not cfg_path.exists():
            return "local", "local-first"
        cfg = load_config(cfg_path)
        memory = getattr(getattr(cfg, "memory", None), "provider", "local")
        agentic = getattr(cfg, "agentic", None)
        flow = getattr(agentic, "flow_mode", None) or getattr(cfg, "flow_mode", None) or "hybrid"
        return str(memory), str(flow)
    except Exception:
        return "local", "unknown"


def _run_status(base: Path) -> tuple[str, str, str]:
    try:
        from opencontext_core.oc_new.store import OcNewStore

        state = OcNewStore(base).latest()
        if state is None:
            return "no active run", "-", "start new change"
        next_action = state.next_action.kind if state.next_action else "done"
        return state.identity.run_id, str(state.current_phase or "done"), next_action
    except Exception:
        return "no active run", "-", "start new change"
