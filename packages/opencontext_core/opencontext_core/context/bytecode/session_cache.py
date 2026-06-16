"""Project-scoped cache of the last AICX bytecode, for cross-turn deltas.

MCP tool calls are stateless, so "the previous turn" is identified by project: the
last bytecode built for a storage path is remembered here, and the next build
diffs against it (see delta.py). Best-effort — a missing or unreadable cache just
means no delta this turn, never an error.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.bytecode.models import ContextBytecode

_FILENAME = "last_bytecode.json"


def _cache_path(storage_path: str | Path) -> Path:
    return Path(storage_path) / _FILENAME


def load_last_bytecode(storage_path: str | Path) -> ContextBytecode | None:
    """Return the previously-saved bytecode for this project, or None."""
    path = _cache_path(storage_path)
    if not path.exists():
        return None
    try:
        return ContextBytecode.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_last_bytecode(storage_path: str | Path, bc: ContextBytecode) -> None:
    """Persist ``bc`` as this project's last bytecode (best-effort)."""
    path = _cache_path(storage_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bc.model_dump_json(), encoding="utf-8")
    except Exception:
        pass
