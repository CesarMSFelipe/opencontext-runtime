"""KG receipts + kg.* event emission (PR-008, KG-14; OC-KG-001 §20-21).

Every significant KG operation (index, query, retrieval, graph update, owner
resolution) produces a receipt and emits the named ``kg.*`` events. This reuses the
global id factory and the ``kg.*`` event-name constants; receipts persist as JSON
under the project storage so a run can be inspected after the fact.

Layering (doc 58): L4 (KG substrate) depending on L0 models and the L1 id factory.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.trace import KG_EVENT_FAMILY
from opencontext_core.runtime.ids import new_receipt_id

KgOperation = Literal["index", "query", "retrieval", "update", "owner"]


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


class KgEvent(BaseModel):
    """One emitted ``kg.*`` event (family ``kg``, doc 59)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Event name, e.g. kg.index.completed.")
    family: str = Field(default=KG_EVENT_FAMILY, description="Event family (always 'kg').")
    timestamp: str = Field(default_factory=_now, description="UTC ISO timestamp.")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Event attributes.")


class KgReceipt(BaseModel):
    """A receipt for one significant KG operation (OC-KG-001 §20)."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str = Field(default_factory=new_receipt_id, description="rcpt_<ulid> id.")
    operation: KgOperation = Field(description="The KG operation this receipt records.")
    status: str = Field(default="ok", description="Operation status (ok/failed).")
    started_at: str = Field(default_factory=_now, description="UTC start timestamp.")
    completed_at: str = Field(default_factory=_now, description="UTC completion timestamp.")
    events: list[str] = Field(default_factory=list, description="Names of kg.* events emitted.")
    details: dict[str, Any] = Field(default_factory=dict, description="Operation detail payload.")
    subgraph_used: bool = Field(
        default=False, description="Whether a KG subgraph served the request."
    )
    broad_file_read: bool = Field(
        default=False, description="Whether a broad file read was needed (KG-CONV)."
    )


class KgObserver:
    """Collects ``kg.*`` events and writes :class:`KgReceipt`s (KG-14, KG-CONV).

    Events accumulate in an in-memory sink (shared list can be injected so a test or
    Studio lane reads them); receipts persist as JSON under ``storage_dir`` when set.
    """

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        event_sink: list[KgEvent] | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir is not None else None
        self.events: list[KgEvent] = event_sink if event_sink is not None else []

    def emit(self, name: str, **attributes: Any) -> KgEvent:
        """Emit a ``kg.*`` event into the sink and return it."""
        event = KgEvent(name=name, attributes=attributes)
        self.events.append(event)
        return event

    def emitted_names(self) -> list[str]:
        """Names of every event emitted so far (in order)."""
        return [e.name for e in self.events]

    def write_receipt(
        self,
        operation: KgOperation,
        *,
        status: str = "ok",
        started_at: str | None = None,
        events: list[str] | None = None,
        subgraph_used: bool = False,
        broad_file_read: bool = False,
        **details: Any,
    ) -> KgReceipt:
        """Build a :class:`KgReceipt`, persist it (when ``storage_dir`` set), return it."""
        receipt = KgReceipt(
            operation=operation,
            status=status,
            started_at=started_at or _now(),
            events=events if events is not None else self.emitted_names(),
            details=details,
            subgraph_used=subgraph_used,
            broad_file_read=broad_file_read,
        )
        if self.storage_dir is not None:
            out_dir = self.storage_dir / "kg" / "receipts"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{receipt.receipt_id}.json"
            path.write_text(json.dumps(receipt.model_dump(), indent=2), encoding="utf-8")
        return receipt
