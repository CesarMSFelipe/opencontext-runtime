"""Governance harness for enterprise-grade execution control.

Enforces data policies, execution limits, and audit trails
for all runtime operations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from opencontext_core.compat import UTC


class DataClassification(Enum):
    """Data sensitivity levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ExecutionAction(Enum):
    """Actions that can be governed."""

    INDEX = "index"
    QUERY = "query"
    CONTEXT_PACK = "context_pack"
    EMBEDDING = "embedding"
    EXPORT = "export"


@dataclass
class ExecutionPolicy:
    """Policy rules for a specific action."""

    action: ExecutionAction
    max_tokens: int | None = None
    max_files: int | None = None
    max_duration_ms: int | None = None
    allowed_data_classes: list[DataClassification] = field(
        default_factory=lambda: [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
        ]
    )
    require_audit: bool = True
    require_redaction: bool = False


@dataclass
class AuditRecord:
    """Immutable audit log entry."""

    record_id: str
    timestamp: datetime
    action: str
    actor: str
    query: str
    tokens_used: int
    data_classification: DataClassification
    policy_applied: str
    result: str
    checksum: str


class GovernanceHarness:
    """Execution harness with enterprise governance."""

    def __init__(
        self,
        db: Any | None = None,
        storage_path: Path | str = ".storage/opencontext/learning",
        policies: list[ExecutionPolicy] | None = None,
    ) -> None:
        self._db = db
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.storage_path / "audit_trail.jsonl"
        self.policies: dict[str, ExecutionPolicy] = {}

        if policies:
            for p in policies:
                self.policies[p.action.value] = p
        else:
            self.policies = {
                "index": ExecutionPolicy(
                    action=ExecutionAction.INDEX,
                    max_tokens=50000,
                    max_files=1000,
                    require_audit=True,
                ),
                "query": ExecutionPolicy(
                    action=ExecutionAction.QUERY,
                    max_tokens=20000,
                    max_files=100,
                    require_audit=True,
                    require_redaction=True,
                ),
                "context_pack": ExecutionPolicy(
                    action=ExecutionAction.CONTEXT_PACK,
                    max_tokens=15000,
                    max_files=50,
                    require_audit=True,
                    require_redaction=True,
                ),
                "embedding": ExecutionPolicy(
                    action=ExecutionAction.EMBEDDING,
                    max_tokens=100000,
                    require_audit=False,
                ),
            }

    def check_policy(
        self,
        action: ExecutionAction | str,
        tokens_estimate: int = 0,
        file_count: int = 0,
        data_classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict[str, Any]:
        """Check if an operation complies with policy."""

        action_str = (
            action.value if isinstance(action, ExecutionAction) else action
        )
        policy = self.policies.get(action_str)

        if not policy:
            return {
                "allowed": True,
                "reason": "No policy defined for this action",
                "limits": {},
            }

        violations: list[str] = []

        if policy.max_tokens and tokens_estimate > policy.max_tokens:
            violations.append(
                f"Token estimate ({tokens_estimate}) exceeds "
                f"maximum ({policy.max_tokens})"
            )

        if policy.max_files and file_count > policy.max_files:
            violations.append(
                f"File count ({file_count}) exceeds "
                f"maximum ({policy.max_files})"
            )

        if data_classification not in policy.allowed_data_classes:
            violations.append(
                f"Data classification '{data_classification.value}' "
                "not allowed for this action"
            )

        return {
            "allowed": len(violations) == 0,
            "reason": "; ".join(violations) if violations else "Policy compliant",
            "limits": {
                "max_tokens": policy.max_tokens,
                "max_files": policy.max_files,
                "requires_redaction": policy.require_redaction,
                "requires_audit": policy.require_audit,
            },
        }

    def audit(
        self,
        action: str,
        actor: str,
        query: str,
        tokens_used: int,
        data_classification: DataClassification,
        result: str,
    ) -> AuditRecord:
        """Create an immutable audit record."""

        import uuid

        timestamp = datetime.now(tz=UTC)
        record_id = str(uuid.uuid4())[:12]

        content = (
            f"{record_id}:{timestamp.isoformat()}:{action}:{actor}:"
            f"{query}:{tokens_used}:{data_classification.value}:{result}"
        )
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

        default_policy = ExecutionPolicy(action=ExecutionAction(action))
        policy_applied = self.policies.get(action, default_policy).action.value
        record = AuditRecord(
            record_id=record_id,
            timestamp=timestamp,
            action=action,
            actor=actor,
            query=query,
            tokens_used=tokens_used,
            data_classification=data_classification,
            policy_applied=policy_applied,
            result=result,
            checksum=checksum,
        )

        self._persist_audit(record)
        return record

    def _persist_audit(self, record: AuditRecord) -> None:
        """Append audit record to DB or JSONL."""

        entry = {
            "record_id": record.record_id,
            "timestamp": record.timestamp.isoformat(),
            "action": record.action,
            "actor": record.actor,
            "query": record.query,
            "tokens_used": record.tokens_used,
            "data_classification": record.data_classification.value,
            "policy_applied": record.policy_applied,
            "result": record.result,
            "checksum": record.checksum,
        }
        if self._db is not None:
            try:
                self._db.insert_audit_record(entry)
                return
            except Exception:
                pass

        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def get_audit_trail(
        self,
        action: str | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[AuditRecord]:
        """Retrieve audit trail with filtering."""

        if self._db is not None:
            try:
                rows = self._db.query_audit_records(action, limit)
                return self._rows_to_records(rows, since)
            except Exception:
                pass
        return self._load_from_jsonl(action, since, limit)

    def _rows_to_records(
        self, rows: list[dict[str, Any]], since: datetime | None
    ) -> list[AuditRecord]:
        """Convert DB rows to AuditRecords."""

        records: list[AuditRecord] = []
        for entry in rows:
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                if since and ts < since:
                    continue
                records.append(
                    AuditRecord(
                        record_id=entry["record_id"],
                        timestamp=ts,
                        action=entry["action"],
                        actor=entry["actor"],
                        query=entry["query"],
                        tokens_used=entry.get("tokens_used", 0) or 0,
                        data_classification=DataClassification(
                            entry["data_classification"]
                        ),
                        policy_applied=entry["policy_applied"],
                        result=entry.get("result", ""),
                        checksum=entry["checksum"],
                    )
                )
            except (KeyError, ValueError):
                continue
        return records

    def _load_from_jsonl(
        self,
        action: str | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[AuditRecord]:
        """Load from JSONL fallback."""

        records: list[AuditRecord] = []
        if not self.audit_file.exists():
            return records

        with open(self.audit_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if action and entry.get("action") != action:
                        continue
                    ts = datetime.fromisoformat(entry["timestamp"])
                    if since and ts < since:
                        continue
                    records.append(
                        AuditRecord(
                            record_id=entry["record_id"],
                            timestamp=ts,
                            action=entry["action"],
                            actor=entry["actor"],
                            query=entry["query"],
                            tokens_used=entry.get("tokens_used", 0),
                            data_classification=DataClassification(
                                entry["data_classification"]
                            ),
                            policy_applied=entry["policy_applied"],
                            result=entry.get("result", ""),
                            checksum=entry["checksum"],
                        )
                    )
                    if len(records) >= limit:
                        break
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        return records

    def verify_integrity(self) -> dict[str, Any]:
        """Verify audit trail integrity by checking checksums."""

        valid = 0
        invalid = 0
        errors: list[str] = []

        if self._db is not None:
            try:
                rows = self._db.query_audit_records(limit=10000)
                for i, entry in enumerate(rows, 1):
                    try:
                        content = (
                            f"{entry['record_id']}:{entry['timestamp']}:"
                            f"{entry['action']}:{entry['actor']}:"
                            f"{entry['query']}:{entry['tokens_used']}:"
                            f"{entry['data_classification']}:{entry['result']}"
                        )
                        expected = hashlib.sha256(
                            content.encode("utf-8")
                        ).hexdigest()[:16]
                        if entry.get("checksum") == expected:
                            valid += 1
                        else:
                            invalid += 1
                            errors.append(f"Row {i}: checksum mismatch")
                    except (KeyError, TypeError):
                        invalid += 1
                        errors.append(f"Row {i}: malformed record")
                return {
                    "status": "valid" if invalid == 0 else "compromised",
                    "valid_records": valid,
                    "invalid_records": invalid,
                    "errors": errors[:10],
                }
            except Exception:
                pass

        if not self.audit_file.exists():
            return {"status": "empty", "valid": 0, "invalid": 0}

        with open(self.audit_file, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    content = (
                        f"{entry['record_id']}:{entry['timestamp']}:"
                        f"{entry['action']}:{entry['actor']}:"
                        f"{entry['query']}:{entry['tokens_used']}:"
                        f"{entry['data_classification']}:{entry['result']}"
                    )
                    expected = hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest()[:16]
                    if entry.get("checksum") == expected:
                        valid += 1
                    else:
                        invalid += 1
                        errors.append(f"Line {i}: checksum mismatch")
                except (json.JSONDecodeError, KeyError):
                    invalid += 1
                    errors.append(f"Line {i}: malformed record")

        return {
            "status": "valid" if invalid == 0 else "compromised",
            "valid_records": valid,
            "invalid_records": invalid,
            "errors": errors[:10],
        }
