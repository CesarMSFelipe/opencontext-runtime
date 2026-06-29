"""AVH-001 fitness guard — no VersionedContract drift without a schema_version bump.

Every ``VersionedContract`` subclass declares a ``schema_version`` literal of the
form ``opencontext.<contract>.v<N>``. This guard snapshots each subclass's declared
field set + its ``schema_version`` (by AST, stdlib only) and diffs it against a
frozen :data:`BASELINE`:

* a field added / removed / renamed WITHOUT bumping ``schema_version`` → FAIL
  (identifies the contract and the field diff);
* the same structural change WITH a bumped ``schema_version`` → PASS (update the
  baseline in the same PR so the next change is guarded again);
* a contract removed from the tree, or a NEW ``VersionedContract`` not in the
  baseline → FAIL (keep the baseline honest).

Same baseline/ratchet philosophy as ``ALLOWED_UPWARD`` in
``test_no_upward_imports.py``: a deliberate, reviewable, source-controlled snapshot.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages/opencontext_core/opencontext_core"
)

#: Frozen snapshot of every VersionedContract subclass: keyed ``"relpath:ClassName"``
#: with its ``schema_version`` literal and sorted declared field names (excluding
#: ``schema_version`` itself, which is tracked as the version). Regenerate when a
#: contract is intentionally changed AND its schema_version is bumped.
BASELINE: dict[str, dict[str, object]] = {
    "evaluation/models.py:BenchmarkSuiteReport": {
        "schema_version": "opencontext.benchmark_suite_report.v1",
        "fields": [
            "changed_files",
            "changed_lines",
            "confidence",
            "duration_ms",
            "measured",
            "notes",
            "receipts",
            "status",
            "success",
            "suite",
            "tokens",
            "tool_calls",
            "version",
        ],
    },
    "evaluation/models.py:EvaluationRecord": {
        "schema_version": "opencontext.evaluation_record.v1",
        "fields": [
            "benchmark_version",
            "escalation_rate",
            "latency_ms",
            "local_validation_pass_rate",
            "patch_size",
            "profile",
            "provider",
            "receipts",
            "repository",
            "retries",
            "runtime_version",
            "stability",
            "success_rate",
            "target_id",
            "target_kind",
            "task",
            "token_count",
            "workflow",
        ],
    },
    "operating_model/release_gate.py:AcceptanceVerdict": {
        "schema_version": "opencontext.acceptance_verdict.v1",
        "fields": [
            "failed",
            "gates",
            "met",
            "methodology_version",
            "not_measured",
            "ready",
        ],
    },
}


def _base_names(cd: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in cd.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def snapshot_contracts() -> dict[str, dict[str, object]]:
    """AST-snapshot every VersionedContract subclass: schema_version + declared fields."""
    snap: dict[str, dict[str, object]] = {}
    for py in ROOT.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(py.relative_to(ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or "VersionedContract" not in _base_names(node):
                continue
            fields: list[str] = []
            schema_version: str | None = None
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    name = stmt.target.id
                    if name == "schema_version":
                        if isinstance(stmt.value, ast.Constant):
                            schema_version = str(stmt.value.value)
                    else:
                        fields.append(name)
            snap[f"{rel}:{node.name}"] = {
                "schema_version": schema_version,
                "fields": sorted(fields),
            }
    return snap


def diff_contracts(
    baseline: dict[str, dict[str, object]], live: dict[str, dict[str, object]]
) -> list[str]:
    """Drift messages: field change w/o bump, removed contract, or new un-baselined contract."""
    msgs: list[str] = []
    for name, base in baseline.items():
        if name not in live:
            msgs.append(f"{name}: contract removed (baseline {base['schema_version']})")
            continue
        cur = live[name]
        base_fields, cur_fields = set(base["fields"]), set(cur["fields"])  # type: ignore[arg-type]
        if base_fields != cur_fields and cur["schema_version"] == base["schema_version"]:
            added = sorted(cur_fields - base_fields)
            removed = sorted(base_fields - cur_fields)
            msgs.append(
                f"{name}: field set changed (added={added} removed={removed}) without a "
                f"schema_version bump ({base['schema_version']}) — bump the version + baseline"
            )
    for name in live:
        if name not in baseline:
            msgs.append(f"{name}: new VersionedContract not in BASELINE — add it (with version)")
    return msgs


def test_no_contract_drift() -> None:
    """Live VersionedContract schema matches the frozen baseline (or version bumped)."""
    drift = diff_contracts(BASELINE, snapshot_contracts())
    assert not drift, "VersionedContract drift detected:\n" + "\n".join(f"  {m}" for m in drift)


def test_field_change_without_bump_fails() -> None:
    """Seeded: a field added with the SAME schema_version is reported as drift."""
    live = {
        k: {"schema_version": v["schema_version"], "fields": list(v["fields"])}  # type: ignore[arg-type]
        for k, v in BASELINE.items()
    }
    victim = "operating_model/release_gate.py:AcceptanceVerdict"
    live[victim]["fields"] = [*live[victim]["fields"], "sneaky_new_field"]  # type: ignore[index]
    drift = diff_contracts(BASELINE, live)
    assert any("sneaky_new_field" in m for m in drift)


def test_field_change_with_bump_passes() -> None:
    """Seeded: the same field change WITH a bumped schema_version is acknowledged (no drift)."""
    live = {
        k: {"schema_version": v["schema_version"], "fields": list(v["fields"])}  # type: ignore[arg-type]
        for k, v in BASELINE.items()
    }
    victim = "operating_model/release_gate.py:AcceptanceVerdict"
    live[victim]["fields"] = [*live[victim]["fields"], "new_field"]  # type: ignore[index]
    live[victim]["schema_version"] = "opencontext.acceptance_verdict.v2"
    assert diff_contracts(BASELINE, live) == []
