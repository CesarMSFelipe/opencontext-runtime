"""AgenticReceipt — extends the oc-new receipt concept with agentic run metadata.

All extended fields are optional so that v1 receipts (without budget/KG/memory data)
remain valid. schema_version is bumped to .v2 to distinguish extended receipts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field


def sha256_file(path: Path | str) -> str | None:
    """Return the hex SHA-256 digest of *path*, or None if the file does not exist."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(directory: Path | str) -> str | None:
    """Return a stable SHA-256 digest over all files in *directory* (sorted).

    Returns None when the directory does not exist or is empty.
    """
    d = Path(directory)
    if not d.exists() or not d.is_dir():
        return None
    h = hashlib.sha256()
    found_any = False
    for file_path in sorted(d.rglob("*")):
        if file_path.is_file():
            found_any = True
            rel = file_path.relative_to(d).as_posix()
            h.update(rel.encode())
            h.update(file_path.read_bytes())
    return h.hexdigest() if found_any else None


class AgenticReceipt(BaseModel, extra="forbid"):
    """Full agentic run receipt, extending the v1 concept with budget and substrate data."""

    schema_version: str = "opencontext.agentic_receipt.v1"
    run_id: str
    change_id: str
    flow_mode: str
    openspec_mode: str
    budget_mode: str
    git_mode: str
    status: str

    # NOTE: Content hashes allow downstream tools to verify artifact integrity.
    context_pack_hash: str | None = None
    kg_snapshot_hash: str | None = None
    compression_report_hash: str | None = None
    budget_ledger_hash: str | None = None
    memory_harvest_hash: str | None = None
    openspec_hash: str | None = None
    git_work_plan_hash: str | None = None

    # NOTE: Extended fields — all optional for v1 compatibility.
    budget_summary: str | None = None
    memory_snapshot_hash: str | None = None
    context_substrate_summary: str | None = None

    # NOTE: v2 identity fields — optional for backward compatibility.
    trace_id: str | None = None
    task: str | None = None
    memory_mode: str | None = None
    preset: str | None = None

    completed_phases: list[str]
    failed_phases: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


if __name__ == "__main__":
    # Minimal receipt (no budget data)
    minimal = AgenticReceipt(
        run_id="ocnew-abc",
        change_id="add-health",
        flow_mode="automatic",
        openspec_mode="off",
        budget_mode="warn",
        git_mode="none",
        status="done",
        completed_phases=["explore", "propose"],
    )
    dumped = minimal.model_dump()
    assert dumped["budget_summary"] is None
    assert dumped["status"] == "done"

    # Full receipt with all extended fields
    full = AgenticReceipt(
        run_id="ocnew-xyz",
        change_id="add-health",
        flow_mode="hybrid",
        openspec_mode="full",
        budget_mode="strict",
        git_mode="single_pr",
        status="done",
        completed_phases=["explore", "spec", "apply"],
        budget_summary="800/1000 tokens used",
        kg_snapshot_hash="abc123",
        memory_snapshot_hash="def456",
        context_substrate_summary="12 files packed",
    )
    assert full.budget_summary == "800/1000 tokens used"
    assert full.kg_snapshot_hash == "abc123"
    assert full.memory_snapshot_hash == "def456"

    print("agentic/receipt.py self-check passed.")
