"""Append-only audit log (REQ-data-gov-005, PR-R2-B).

The audit log is the only place where the original ``record_id`` of a purged
or redacted artifact is preserved. Every redaction, every purge, every
residency switch is written as one JSON object per line to
``<base>/audit/dec_<ulid>.jsonl``.

Tamper-evidence uses a SHA-256 hash chain: each line carries
``_prev_hash`` (the hash of the prior line) and ``_self_hash``
(sha256 of the line with ``_self_hash`` set to zero). The first line's
``_prev_hash`` is the all-zeros anchor. :meth:`AuditLog.verify` walks the
chain and returns ``False`` if any line was rewritten.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_core.governance.classification import DataSensitivity
from opencontext_core.runtime.ids import new_decision_id

__all__ = ["AuditLog", "AuditRecord"]


_ANCHOR_HASH = "0" * 64


@dataclass
class AuditRecord:
    """One audit event."""

    record_id: str
    actor: str
    action: str
    sensitivity: DataSensitivity
    detail: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())


def _line_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of a line payload, sorted keys, no whitespace."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AuditLog:
    """Append-only JSONL log under ``<base_dir>/audit/dec_<ulid>.jsonl``."""

    def __init__(self, base_dir: Path | str) -> None:
        self._base = Path(base_dir)
        self._audit_dir = self._base / "audit"
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        # One file per AuditLog instance — matches the spec's "dec_<ulid>.jsonl" filename.
        self._file = self._audit_dir / f"{new_decision_id()}.jsonl"

    @property
    def path(self) -> Path:
        return self._file

    def _read_existing_chain(self) -> list[str]:
        if not self._file.exists():
            return []
        return self._file.read_text(encoding="utf-8").splitlines()

    def _prev_hash(self) -> str:
        existing = self._read_existing_chain()
        if not existing:
            return _ANCHOR_HASH
        last = json.loads(existing[-1])
        return str(last.get("_self_hash", _ANCHOR_HASH))

    def append(self, record: AuditRecord) -> None:
        payload = asdict(record)
        # Ensure sensitivity is a string for JSON portability.
        sensitivity = payload.get("sensitivity")
        if isinstance(sensitivity, DataSensitivity):
            payload["sensitivity"] = sensitivity.value
        payload["_prev_hash"] = self._prev_hash()
        # Self-hash is over the payload with _self_hash = "0" placeholder.
        with open(self._file, "a", encoding="utf-8") as fh:
            placeholder = dict(payload)
            placeholder["_self_hash"] = "0" * 64
            payload["_self_hash"] = _line_hash(placeholder)
            fh.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            fh.write("\n")

    def query(
        self,
        *,
        sensitivity: DataSensitivity | str | None = None,
        actor: str | None = None,
        action: str | None = None,
    ) -> list[AuditRecord]:
        existing = self._read_existing_chain()
        results: list[AuditRecord] = []
        for line in existing:
            if not line.strip():
                continue
            payload = json.loads(line)
            if sensitivity is not None:
                want = (
                    sensitivity.value
                    if isinstance(sensitivity, DataSensitivity)
                    else str(sensitivity)
                )
                if payload.get("sensitivity") != want:
                    continue
            if actor is not None and payload.get("actor") != actor:
                continue
            if action is not None and payload.get("action") != action:
                continue
            payload.pop("_prev_hash", None)
            payload.pop("_self_hash", None)
            sens = payload.get("sensitivity")
            if sens is not None:
                payload["sensitivity"] = DataSensitivity(sens)
            results.append(AuditRecord(**payload))
        return results

    def verify(self) -> bool:
        existing = self._read_existing_chain()
        if not existing:
            return True
        prev = _ANCHOR_HASH
        for line in existing:
            if not line.strip():
                continue
            payload = json.loads(line)
            stored_self = payload.get("_self_hash")
            stored_prev = payload.get("_prev_hash")
            if stored_prev != prev:
                return False
            # Re-hash with _self_hash zeroed. Keep _prev_hash in the placeholder
            # so the hash matches what was committed at append time.
            placeholder = dict(payload)
            placeholder["_self_hash"] = "0" * 64
            if _line_hash(placeholder) != stored_self:
                return False
            prev = stored_self
        return True

    def all_records(self) -> Iterable[AuditRecord]:
        """Return every record in append order (debug + test helper)."""
        return self.query()
