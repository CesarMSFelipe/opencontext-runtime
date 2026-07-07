"""RunReceiptStore — file-backed store for RunReceipt records.

Also hosts the PR-012 provider receipts (book §25 "Receipts"):
``provider-selection`` / ``provider-call`` / ``fallback`` / ``cost``. These are
persisted to a sibling ``provider_receipts.jsonl`` so they never collide with the
run-id-keyed ``receipts.jsonl`` lookups.
"""

from __future__ import annotations

import builtins
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.operating_model.team import RunReceipt
from opencontext_core.paths import StorageMode, execution_state, resolve_workspace_path
from opencontext_core.runtime.ids import new_id

# NOTE: pruning strategy not yet implemented (Phase 2+)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class ProviderReceipt(BaseModel):
    """A provider lifecycle receipt (book §25 "Receipts").

    ``receipt_id`` uses the ``pcall_<ulid>`` provider-call id scheme (doc 59
    §Global IDs). One model covers the four receipt kinds; unused numeric fields
    default to ``0``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.provider_receipt.v1"
    receipt_id: str = Field(default_factory=lambda: new_id("pcall"))
    kind: Literal["provider-selection", "provider-call", "fallback", "cost"]
    provider: str
    model: str = ""
    routing_reason: str = ""
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_s: float = Field(default=0.0, ge=0.0)
    retries: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    cache_hit: bool = False
    error: str | None = None
    created_at: str = Field(default_factory=_now_iso)


class RunReceiptStore:
    """Append-only JSONL store for RunReceipt objects."""

    def __init__(self, root: Path | str = ".") -> None:
        # ``root`` is the PROJECT root; receipts live under the active workspace
        # (user-mode XDG by default; legacy ``.opencontext/receipts`` in local
        # mode). Created lazily on first save so an unused store leaves no
        # empty dir. Reads fall back to the legacy in-repo ledger for receipts
        # persisted before execution state moved to user-mode storage.
        self.base_path = execution_state.receipts_root(Path(root))
        self._store = self.base_path / "receipts.jsonl"
        self._legacy_store = (
            resolve_workspace_path(Path(root), StorageMode.local) / "receipts" / "receipts.jsonl"
        )

    def _ledgers(self) -> builtins.list[Path]:
        """Existing receipt ledgers, active location first, legacy fallback second."""
        candidates = [self._store]
        if self._legacy_store != self._store:
            candidates.append(self._legacy_store)
        return [p for p in candidates if p.exists()]

    def save(self, receipt: RunReceipt) -> Path:
        self.base_path.mkdir(parents=True, exist_ok=True)
        with self._store.open("a", encoding="utf-8") as fh:
            fh.write(receipt.model_dump_json() + "\n")
        return self._store

    def load(self, run_id: str) -> RunReceipt:
        import json

        for ledger in self._ledgers():
            with ledger.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("run_id") == run_id:
                        return RunReceipt.model_validate(data)
        raise FileNotFoundError(f"Run receipt not found: {run_id}")

    def list(self) -> list[RunReceipt]:
        receipts: list[RunReceipt] = []
        seen: set[str] = set()
        import json

        for ledger in self._ledgers():
            with ledger.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rid = data.get("run_id", "")
                        if rid not in seen:
                            seen.add(rid)
                            receipts.append(RunReceipt.model_validate(data))
                    except Exception:
                        continue
        return receipts

    def verify(self, run_id: str) -> dict[str, object]:
        try:
            receipt = self.load(run_id)
        except FileNotFoundError:
            return {"run_id": run_id, "ok": False, "error": "not_found"}
        return {
            "run_id": receipt.run_id,
            "schema_version": receipt.schema_version,
            "ok": True,
            "checks": {
                "policy_hash_present": bool(receipt.policy_hash),
                "context_pack_hash_present": bool(receipt.context_pack_hash),
                "prompt_hash_present": bool(receipt.prompt_hash),
                "trace_id_present": bool(receipt.trace_id),
            },
        }

    # --- PR-012 provider receipts (book §25 "Receipts") -------------------- #

    @property
    def _provider_store(self) -> Path:
        return self.base_path / "provider_receipts.jsonl"

    def save_provider_receipt(self, receipt: ProviderReceipt) -> Path:
        """Append one provider receipt (append-only JSONL)."""

        store = self._provider_store
        store.parent.mkdir(parents=True, exist_ok=True)
        with store.open("a", encoding="utf-8") as fh:
            fh.write(receipt.model_dump_json() + "\n")
        return store

    # NOTE: the return annotation uses ``builtins.list`` because this class
    # defines a method named ``list`` that shadows the builtin in class scope.
    def list_provider_receipts(self) -> builtins.list[ProviderReceipt]:
        """Return every persisted provider receipt, in append order."""

        store = self._provider_store
        if not store.exists():
            return []
        receipts: list[ProviderReceipt] = []
        with store.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    receipts.append(ProviderReceipt.model_validate(json.loads(line)))
                except Exception:
                    continue
        return receipts
