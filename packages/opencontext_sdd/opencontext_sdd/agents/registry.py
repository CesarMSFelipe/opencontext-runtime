"""Canonical 18-host-client Adapter registry.

Single source of truth for the SDD orchestrator's client-adapter map. The
18 ids mirror the runtime config (``active_clients``) plus the long-tail
entries (``hermes``). Each entry is a concrete ``Adapter`` subclass
generated programmatically; real behaviour lands in PR3/PR4 alongside the
CLI + FastAPI surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_sdd.agents.interface import Adapter


def _make(adapter_id: str, display: str = "", paths: tuple[str, ...] = ()) -> type[Adapter]:
    def _not_configured(self: Adapter) -> dict[str, Any]:
        return {"status": "not_configured", "adapter": adapter_id}

    def _change(self: Adapter, change: str) -> dict[str, Any]:
        return {"status": "not_configured", "adapter": adapter_id, "change": change}

    cls_name = "".join(part.title() for part in adapter_id.split("-")) + "Adapter"
    cls: type[Adapter] = type(
        cls_name,
        (Adapter,),
        {
            "id": adapter_id,
            "display_name": display or adapter_id,
            "config_paths": paths,
            "install": _not_configured,
            "uninstall": _not_configured,
            "status": _not_configured,
            "sync_state": _not_configured,
            "apply": _change,
            "verify": _change,
        },
    )
    return cls


class ClaudeCodeAdapter(Adapter):
    """Real adapter for Claude Code that syncs memory and exposes substrate hash (S2+S3).

    Constructor parameters are optional; defaults work for a standard install.

    Parameters
    ----------
    project_root:
        Root directory of the project to sync memory for.  Defaults to ``"."``.
    export_path:
        Destination JSON file for the memory export.  Defaults to
        ``<project_root>/.opencontext/memory_sync.json``.
    """

    id: str = "claude-code"
    display_name: str = "Claude Code"
    config_paths: tuple[str, ...] = ("~/.claude/",)

    def __init__(
        self,
        project_root: Path | str | None = None,
        export_path: Path | str | None = None,
    ) -> None:
        self._root = Path(project_root) if project_root is not None else Path(".")
        if export_path is not None:
            self._export_path = Path(export_path)
        else:
            self._export_path = self._root / ".opencontext" / "memory_sync.json"

    def install(self) -> dict[str, Any]:
        return {"status": "not_configured", "adapter": self.id}

    def uninstall(self) -> dict[str, Any]:
        return {"status": "not_configured", "adapter": self.id}

    def status(self) -> dict[str, Any]:
        return {"status": "not_configured", "adapter": self.id}

    def sync_state(self) -> dict[str, Any]:
        """Export project memory and return the latest context_pack_hash (S2+S3).

        Returns
        -------
        dict with keys:
            status: "ok" on success
            exported: number of memory items written
            path: str path to the exported JSON file
            context_pack_hash: latest substrate hash, or None if not yet built
        """
        from opencontext_core.memory.transfer import memory_export
        from opencontext_core.memory_usability.context_repository import (
            ContextRepository,
        )

        repo = ContextRepository(self._root)
        try:
            exported = memory_export(repo, str(self._export_path))
        except Exception as exc:
            return {
                "status": "error",
                "adapter": self.id,
                "error": str(exc),
            }

        # S2: read the latest substrate report to expose the context_pack_hash.
        context_pack_hash: str | None = None
        try:
            from opencontext_core.config_resolver import resolve_active_storage_path

            report_path = resolve_active_storage_path(self._root) / "substrate_report.json"
            if report_path.exists():
                data = json.loads(report_path.read_text(encoding="utf-8"))
                context_pack_hash = data.get("context_pack_hash")
        except Exception:
            pass  # Best-effort; never fail sync_state.

        return {
            "status": "ok",
            "adapter": self.id,
            "exported": exported,
            "path": str(self._export_path),
            "context_pack_hash": context_pack_hash,
        }

    def apply(self, change: str) -> dict[str, Any]:
        return {"status": "not_configured", "adapter": self.id, "change": change}

    def verify(self, change: str) -> dict[str, Any]:
        return {"status": "not_configured", "adapter": self.id, "change": change}


# NOTE: 18 ids = active_clients (17) + hermes.
ADAPTERS: dict[str, type[Adapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "opencode": _make("opencode", "opencode CLI", ("~/.config/opencode/",)),
    "kilo-code": _make("kilo-code", "Kilo Code", ("~/.config/kilo/",)),
    "gemini-cli": _make("gemini-cli", "Gemini CLI", ("~/.config/gemini/",)),
    "cursor": _make("cursor", "Cursor", ("~/.cursor/",)),
    "vscode-copilot": _make("vscode-copilot", "VS Code Copilot", ("~/.vscode/",)),
    "copilot-cli": _make("copilot-cli", "Copilot CLI", ("~/.copilot/",)),
    "codex": _make("codex", "OpenAI Codex", ("~/.codex/",)),
    "windsurf": _make("windsurf", "Windsurf", ("~/.codeium/windsurf/",)),
    "antigravity": _make("antigravity", "Antigravity", ("~/.antigravity/",)),
    "kimi-code": _make("kimi-code", "Kimi Code", ("~/.config/kimi/",)),
    "qwen-code": _make("qwen-code", "Qwen Code", ("~/.config/qwen/",)),
    "kiro-ide": _make("kiro-ide", "Kiro IDE", ("~/.kiro/ide/",)),
    "kiro": _make("kiro", "Kiro", ("~/.kiro/",)),
    "openclaw": _make("openclaw", "OpenClaw", ("~/.openclaw/",)),
    "pi": _make("pi", "Pi", ("~/.pi/",)),
    "cline": _make("cline", "Cline", ("~/.config/cline/",)),
    "hermes": _make("hermes", "Hermes", ("~/.hermes/",)),
}


def register(cls: type, *, name: str | None = None, replace: bool = False) -> str:
    """Register ``cls`` under ``name`` (defaults to ``cls.id``).

    Raises ``ValueError("duplicate adapter id: <key>")`` if the key exists
    and ``replace`` is False.
    """
    key = name or str(getattr(cls, "id", ""))
    if not key:
        raise ValueError("register: adapter name is required (cls.id or name=...)")
    if not replace and key in ADAPTERS:
        raise ValueError(f"duplicate adapter id: {key!r}")
    ADAPTERS[key] = cls
    return key


__all__ = ["ADAPTERS", "ClaudeCodeAdapter", "register"]
