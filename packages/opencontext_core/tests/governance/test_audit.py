"""Append-only audit log (REQ-data-gov-005, PR-R2-B).

Every redaction, purge, and residency switch is written to
``audit/dec_<ulid>.jsonl`` — one JSON object per line, append-only.

Tampering with any historical line is detected by :meth:`AuditLog.verify`
via per-line SHA-256 hashes recorded in the first line of the file
("anchor + leaf chain" — same shape as the decision log recorder).
"""

from __future__ import annotations

from opencontext_core.governance.audit import AuditLog, AuditRecord
from opencontext_core.governance.classification import DataSensitivity


class TestAuditRecordShape:
    def test_record_carries_required_fields(self) -> None:
        rec = AuditRecord(
            record_id="r1",
            actor="redaction_pipeline",
            action="redact",
            sensitivity=DataSensitivity.CONFIDENTIAL,
            detail={"tag": "<REDACTED:abc123>"},
        )
        assert rec.record_id == "r1"
        assert rec.actor == "redaction_pipeline"
        assert rec.action == "redact"
        assert rec.sensitivity is DataSensitivity.CONFIDENTIAL
        assert rec.detail == {"tag": "<REDACTED:abc123>"}
        assert rec.timestamp  # auto-filled


class TestAuditLogFileCreation:
    def test_creates_dec_ulid_jsonl_under_audit_dir(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append(
            AuditRecord(
                record_id="r1",
                actor="redaction_pipeline",
                action="redact",
                sensitivity=DataSensitivity.CONFIDENTIAL,
            )
        )
        files = list((tmp_path / "audit").glob("dec_*.jsonl"))
        assert len(files) == 1
        # ULID: 26 chars after dec_, Crockford base32.
        assert files[0].name.startswith("dec_")
        assert files[0].name.endswith(".jsonl")
        stem = files[0].stem[len("dec_") :]
        assert len(stem) == 26

    def test_multiple_appends_grow_file_and_keep_anchor(self, tmp_path):
        log = AuditLog(tmp_path)
        for i in range(3):
            log.append(
                AuditRecord(
                    record_id=f"r{i}",
                    actor="redaction_pipeline",
                    action="redact",
                    sensitivity=DataSensitivity.INTERNAL,
                )
            )
        files = list((tmp_path / "audit").glob("dec_*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3


class TestAuditLogQuery:
    def test_query_by_sensitivity(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append(
            AuditRecord(
                record_id="r1",
                actor="redaction_pipeline",
                action="redact",
                sensitivity=DataSensitivity.RESTRICTED,
            )
        )
        log.append(
            AuditRecord(
                record_id="r2",
                actor="policy_engine",
                action="redact",
                sensitivity=DataSensitivity.PUBLIC,
            )
        )
        log.append(
            AuditRecord(
                record_id="r3",
                actor="redaction_pipeline",
                action="purge",
                sensitivity=DataSensitivity.RESTRICTED,
            )
        )
        restricted = log.query(sensitivity=DataSensitivity.RESTRICTED)
        assert [r.record_id for r in restricted] == ["r1", "r3"]
        assert all(r.sensitivity is DataSensitivity.RESTRICTED for r in restricted)

    def test_query_by_actor(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append(
            AuditRecord(
                record_id="r1",
                actor="redaction_pipeline",
                action="redact",
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
        log.append(
            AuditRecord(
                record_id="r2",
                actor="retention",
                action="purge",
                sensitivity=DataSensitivity.CONFIDENTIAL,
            )
        )
        assert [r.record_id for r in log.query(actor="retention")] == ["r2"]

    def test_query_by_action(self, tmp_path):
        log = AuditLog(tmp_path)
        log.append(
            AuditRecord(
                record_id="r1",
                actor="redaction_pipeline",
                action="redact",
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
        log.append(
            AuditRecord(
                record_id="r2",
                actor="retention",
                action="purge",
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
        assert [r.record_id for r in log.query(action="purge")] == ["r2"]

    def test_query_empty_filter_returns_all(self, tmp_path):
        log = AuditLog(tmp_path)
        for i in range(5):
            log.append(
                AuditRecord(
                    record_id=f"r{i}",
                    actor="x",
                    action="y",
                    sensitivity=DataSensitivity.INTERNAL,
                )
            )
        assert len(log.query()) == 5


class TestAuditLogVerify:
    def test_verify_passes_on_pristine_log(self, tmp_path):
        log = AuditLog(tmp_path)
        for i in range(3):
            log.append(
                AuditRecord(
                    record_id=f"r{i}",
                    actor="x",
                    action="y",
                    sensitivity=DataSensitivity.INTERNAL,
                )
            )
        assert log.verify() is True

    def test_verify_detects_tampered_line(self, tmp_path):
        log = AuditLog(tmp_path)
        for i in range(3):
            log.append(
                AuditRecord(
                    record_id=f"rec-{i:03d}",
                    actor="x",
                    action="y",
                    sensitivity=DataSensitivity.INTERNAL,
                )
            )
        log_file = next((tmp_path / "audit").glob("dec_*.jsonl"))
        text = log_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        # Mutate a non-anchor line: change the record_id in the middle of the file.
        target_idx = 1
        original = lines[target_idx]
        # The second record has id rec-001; replace it.
        tampered = original.replace('"record_id":"rec-001"', '"record_id":"rec-TAMPERED"', 1)
        assert tampered != original, "test data must contain a record_id we can replace"
        lines[target_idx] = tampered
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert log.verify() is False
