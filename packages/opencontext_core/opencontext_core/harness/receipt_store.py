"""Append-only, immutable ReceiptStore (PR-002, L2).

Implements the book receipt CRUD (doc 24 §7) over append-only JSONL
(``receipts/receipts.jsonl``), mirroring the shipped
``operating_model.receipts.RunReceiptStore`` pattern. A written receipt is never
mutated in place (doc 24 §15): a superseding receipt is simply another appended
line, so the original survives unchanged.

Stores the three durable receipt models (book :class:`Receipt`,
:class:`ApplyReceipt`, :class:`RollbackReceipt`); each line is re-parsed by its
``schema_version`` on read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from opencontext_core.models.receipt import (
    ApplyReceipt,
    PhaseReceipt,
    Receipt,
    RollbackReceipt,
)
from opencontext_core.models.run_manifest import ReceiptRef

ReceiptLike = Receipt | ApplyReceipt | RollbackReceipt | PhaseReceipt

_BY_SCHEMA: dict[str, type[BaseModel]] = {
    "opencontext.receipt.v1": Receipt,
    "opencontext.apply_receipt.v1": ApplyReceipt,
    "opencontext.rollback_receipt.v1": RollbackReceipt,
    "opencontext.phase_receipt.v1": PhaseReceipt,
}


class ReceiptStore:
    """Per-run append-only JSONL receipt store (immutable lines)."""

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)
        self.receipts_dir = self.run_dir / "receipts"
        self._jsonl = self.receipts_dir / "receipts.jsonl"

    @property
    def path(self) -> Path:
        return self._jsonl

    def write(self, receipt: ReceiptLike) -> ReceiptRef:
        """Append one receipt line (never rewrites priors) and return its ref."""
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        with self._jsonl.open("a", encoding="utf-8") as handle:
            handle.write(receipt.model_dump_json() + "\n")
        rel = self._jsonl.relative_to(self.run_dir).as_posix()
        return ReceiptRef(
            receipt_id=receipt.receipt_id,
            path=rel,
            kind=getattr(receipt, "kind", None),
        )

    def _iter(self) -> list[ReceiptLike]:
        if not self._jsonl.exists():
            return []
        out: list[ReceiptLike] = []
        for line in self._jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            model = _BY_SCHEMA.get(str(data.get("schema_version")))
            if model is None:
                continue
            try:
                out.append(cast(ReceiptLike, model.model_validate(data)))
            except ValueError:
                continue
        return out

    def get(self, receipt_id: str) -> ReceiptLike:
        """Return the first receipt with *receipt_id*, or raise ``KeyError``."""
        for receipt in self._iter():
            if receipt.receipt_id == receipt_id:
                return receipt
        raise KeyError(receipt_id)

    def list_for_run(self, run_id: str) -> list[Receipt]:
        """Return the book :class:`Receipt`s recorded for *run_id*, in order."""
        return [r for r in self._iter() if isinstance(r, Receipt) and r.run_id == run_id]

    def list_apply_receipts(self) -> list[ApplyReceipt]:
        """Return every :class:`ApplyReceipt` in append order."""
        return [r for r in self._iter() if isinstance(r, ApplyReceipt)]

    def list_rollback_receipts(self) -> list[RollbackReceipt]:
        """Return every :class:`RollbackReceipt` in append order."""
        return [r for r in self._iter() if isinstance(r, RollbackReceipt)]

    def list_phase_receipts(self) -> list[PhaseReceipt]:
        """Return every per-phase :class:`PhaseReceipt` in append order."""
        return [r for r in self._iter() if isinstance(r, PhaseReceipt)]

    def list_all(self) -> list[ReceiptLike]:
        """Return every stored receipt of any kind, in append order."""
        return self._iter()
