"""Plugin observability — events + receipts (PR-015, SPEC PR-015-OBS).

Every lifecycle stage and every contribution emits an observable event, and a
plugin activation produces a receipt referencing the plugin id and the affected
extension points. Events carry the ``plugin`` family (doc 59 event hierarchy) so
Studio can render a per-family lane. Reuses ``agentic/receipt.py`` for the
content-hash helper rather than introducing a new receipt store.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.agentic.receipt import sha256_tree

# Event family for plugin events (doc 59: 11 RuntimeEvent families).
PLUGIN_EVENT_FAMILY = "plugin"
PLUGIN_RECEIPT_SCHEMA = "opencontext.plugin_receipt.v1"


class ContributionRecord(BaseModel):
    """One observable contribution: which extension point, which id, which plugin."""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str = Field(description="Owning plugin id.")
    extension_point: str = Field(description="Extension point the contribution targets.")
    contribution_id: str = Field(description="Contribution id.")


class PluginEvent(BaseModel):
    """An observable plugin lifecycle/contribution event (family='plugin')."""

    model_config = ConfigDict(extra="forbid")

    family: str = Field(default=PLUGIN_EVENT_FAMILY)
    type: str = Field(description="Stage name or 'contribution'.")
    plugin_id: str = Field(description="Plugin the event refers to.")
    status: str = Field(default="", description="Stage outcome, when applicable.")
    extension_point: str | None = Field(default=None)
    contribution_id: str | None = Field(default=None)
    detail: str = Field(default="")


class PluginReceipt(BaseModel):
    """Receipt for a plugin activation run (referenced by id + contributions)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=PLUGIN_RECEIPT_SCHEMA)
    plugin_id: str
    status: str
    stages: list[str] = Field(default_factory=list)
    contributions: list[ContributionRecord] = Field(default_factory=list)
    reason: str = ""
    plugin_dir_hash: str | None = Field(
        default=None, description="sha256 over the plugin dir (provenance)."
    )


class PluginObserver:
    """Collects plugin events; the lifecycle emits through it.

    In-memory by default (testable, no IO). Callers may persist the receipt; the
    observer itself stays side-effect-free so a failing sink never aborts the
    runtime (SPEC PR-015-ISOLATION).
    """

    def __init__(self) -> None:
        self.events: list[PluginEvent] = []

    def emit(self, event: PluginEvent) -> None:
        self.events.append(event)

    def emit_stage(self, stage: str, plugin_id: str, *, status: str = "", detail: str = "") -> None:
        self.emit(PluginEvent(type=stage, plugin_id=plugin_id, status=status, detail=detail))

    def emit_contribution(self, record: ContributionRecord) -> None:
        self.emit(
            PluginEvent(
                type="contribution",
                plugin_id=record.plugin_id,
                extension_point=record.extension_point,
                contribution_id=record.contribution_id,
            )
        )


def build_receipt(
    plugin_id: str,
    *,
    status: str,
    stages: list[str],
    contributions: list[ContributionRecord],
    reason: str = "",
    plugin_dir: Path | None = None,
) -> PluginReceipt:
    """Build a :class:`PluginReceipt` for an activation run."""
    dir_hash = sha256_tree(plugin_dir) if plugin_dir is not None else None
    return PluginReceipt(
        plugin_id=plugin_id,
        status=status,
        stages=stages,
        contributions=contributions,
        reason=reason,
        plugin_dir_hash=dir_hash,
    )
