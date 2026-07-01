"""Canonical 18-host-client Adapter registry.

Single source of truth for the SDD orchestrator's client-adapter map. The
18 ids mirror the runtime config (``active_clients``) plus the long-tail
entries (``hermes``). Each entry is a concrete ``Adapter`` subclass
generated programmatically; real behaviour lands in PR3/PR4 alongside the
CLI + FastAPI surface.
"""

from __future__ import annotations

from typing import Any

from opencontext_sdd.agents.interface import Adapter


def _make(adapter_id: str, display: str = "", paths: tuple[str, ...] = ()) -> type[Adapter]:
    def _noop(self: Adapter) -> dict[str, Any]:
        return {"status": "noop", "adapter": adapter_id}

    def _change(self: Adapter, change: str) -> dict[str, Any]:
        return {"status": "noop", "adapter": adapter_id, "change": change}

    cls_name = "".join(part.title() for part in adapter_id.split("-")) + "Adapter"
    cls: type[Adapter] = type(
        cls_name,
        (Adapter,),
        {
            "id": adapter_id,
            "display_name": display or adapter_id,
            "config_paths": paths,
            "install": _noop,
            "uninstall": _noop,
            "status": _noop,
            "sync_state": _noop,
            "apply": _change,
            "verify": _change,
        },
    )
    return cls


# ponytail: 18 ids = active_clients (17) + hermes.
ADAPTERS: dict[str, type[Adapter]] = {
    "claude-code": _make("claude-code", "Claude Code", ("~/.claude/",)),
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


__all__ = ["ADAPTERS", "register"]
