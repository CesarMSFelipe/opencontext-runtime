"""Tests for the canonical SDD Status Pydantic model (REQ-OSS-001/002/003).

Per strict-TDD: this file is the source of truth for the Status model
contract. The model in ``opencontext_sdd.status`` is written to satisfy
these tests.

T1.5 — ``test_REQ_OSS_001_*`` written first.
T1.7 — Resolve + parse_verify_report tests added RED-first; status.py
        extended in T1.7 GREEN to make them pass.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_sdd.status import Resolve, Status, parse_verify_report

# ---------------------------------------------------------------------------
# REQ-OSS-001 — schemaName and 14-field round-trip (T1.5)
# ---------------------------------------------------------------------------


def test_REQ_OSS_001_default_schema_name_and_14_fields_round_trip() -> None:
    """A fresh Status has the canonical schema name, and a fully-populated
    Status round-trips through JSON with all 14 fields preserved."""
    fresh = Status()
    assert fresh.schemaName == "opencontext.sdd-status"
    assert fresh.schemaVersion == 1

    populated = Status(
        changeName="agentic-parity-engram-gentle",
        artifactStore="hybrid",
        planningHome="openspec",
        changeRoot="openspec/changes/agentic-parity-engram-gentle",
        artifactPaths={
            "proposal": "openspec/changes/agentic-parity-engram-gentle/proposal.md",
            "design": "openspec/changes/agentic-parity-engram-gentle/design.md",
        },
        artifacts={"proposal": "done", "design": "partial", "tasks": "missing"},
        taskProgress={"total": 12, "done": 1},
        dependencies={"pr1": "opencontext-core", "pr2": "opencontext-memory"},
        applyState="running",
        actionContext={"allowedEditRoots": ["packages/opencontext_sdd"]},
        relationships={"extends": "opencontext-core.sdd_runtime"},
        nextRecommended="design",
        blockedReasons=["artifact:partial:design"],
    )
    raw = populated.model_dump_json()
    reparsed = Status.model_validate_json(raw)
    assert reparsed == populated
    # The 14 top-level fields are all present in the JSON payload.
    payload = json.loads(raw)
    expected_keys = {
        "schemaName",
        "schemaVersion",
        "changeName",
        "artifactStore",
        "planningHome",
        "changeRoot",
        "artifactPaths",
        "artifacts",
        "taskProgress",
        "dependencies",
        "applyState",
        "actionContext",
        "relationships",
        "nextRecommended",
        "blockedReasons",
    }
    assert expected_keys.issubset(payload.keys())
    assert len(payload) == len(expected_keys)


# ---------------------------------------------------------------------------
# REQ-OSS-002 — Resolve next-phase from disk artifacts (T1.7)
# ---------------------------------------------------------------------------


def _write_minimal_change(change_root: Path) -> None:
    change_root.mkdir(parents=True, exist_ok=True)
    (change_root / "proposal.md").write_text("# proposal\n", encoding="utf-8")


def test_REQ_OSS_002_resolve_no_proposal_returns_propose(tmp_path: Path) -> None:
    """A change dir without ``proposal.md`` resolves to ``propose``."""
    changes = tmp_path / "openspec" / "changes"
    (changes / "demo").mkdir(parents=True)

    status = Resolve("demo", cwd=str(tmp_path))
    assert status.changeName == "demo"
    assert status.nextRecommended == "propose"
    assert "missing:proposal.md" in status.blockedReasons
    assert status.artifacts["proposal"] == "missing"


def test_REQ_OSS_002_resolve_all_done_with_pass_verdict_returns_archive(
    tmp_path: Path,
) -> None:
    """A complete change with a passing verify report resolves to ``archive``."""
    changes = tmp_path / "openspec" / "changes" / "demo"
    _write_minimal_change(changes)
    (changes / "design.md").write_text("# design\n", encoding="utf-8")
    (changes / "tasks.md").write_text("- [x] done\n", encoding="utf-8")
    (changes / "specs" / "demo-cap").mkdir(parents=True)
    (changes / "specs" / "demo-cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (changes / "verify-report.md").write_text("verdict: PASS\n", encoding="utf-8")

    status = Resolve("demo", cwd=str(tmp_path))
    assert status.nextRecommended == "archive"
    assert status.blockedReasons == []
    assert status.applyState == "done"


def test_REQ_OSS_002_resolve_ambiguous_when_multiple_changes_and_none(
    tmp_path: Path,
) -> None:
    """``Resolve(None, ...)`` with two change dirs is ambiguous."""
    changes = tmp_path / "openspec" / "changes"
    (changes / "alpha").mkdir(parents=True)
    (changes / "beta").mkdir(parents=True)

    status = Resolve(None, cwd=str(tmp_path))
    assert status.changeName is None
    assert "ambiguous:select-change" in status.blockedReasons
    assert status.nextRecommended == "select-change"


# ---------------------------------------------------------------------------
# Resolve routing truth table — intermediate planning states (parity with
# gentle-ai's sddstatus dispatcher). Each seeds a partial change dir on disk and
# asserts the exact nextRecommended, so a regression in the decision tree fails
# here instead of misrouting a real SDD run.
# ---------------------------------------------------------------------------


def _seed(cwd: Path, *rel_files: str) -> None:
    """Create ``openspec/changes/demo/`` with the given relative files."""
    root = cwd / "openspec" / "changes" / "demo"
    root.mkdir(parents=True, exist_ok=True)
    for rel in rel_files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("- [x] done\n" if rel == "tasks.md" else "# x\n", encoding="utf-8")


def test_resolve_proposal_only_routes_to_spec(tmp_path: Path) -> None:
    _seed(tmp_path, "proposal.md")
    assert Resolve("demo", cwd=str(tmp_path)).nextRecommended == "spec"


def test_resolve_specs_without_design_routes_to_design(tmp_path: Path) -> None:
    _seed(tmp_path, "proposal.md", "specs/cap/spec.md")
    assert Resolve("demo", cwd=str(tmp_path)).nextRecommended == "design"


def test_resolve_design_without_tasks_routes_to_apply(tmp_path: Path) -> None:
    # OC routes a missing tasks.md straight to apply (its decision tree has no
    # standalone 'tasks' planning state — documents OC's real behavior).
    _seed(tmp_path, "proposal.md", "specs/cap/spec.md", "design.md")
    status = Resolve("demo", cwd=str(tmp_path))
    assert status.nextRecommended == "apply"
    assert status.applyState == "running"


def test_resolve_pending_tasks_routes_to_apply(tmp_path: Path) -> None:
    _seed(tmp_path, "proposal.md", "specs/cap/spec.md", "design.md")
    (tmp_path / "openspec" / "changes" / "demo" / "tasks.md").write_text(
        "- [x] one\n- [ ] two\n", encoding="utf-8"
    )
    assert Resolve("demo", cwd=str(tmp_path)).nextRecommended == "apply"


def test_resolve_all_tasks_done_no_verify_report_routes_to_verify(tmp_path: Path) -> None:
    """All tasks complete but never verified must route to verify, NOT archive.

    Regression: the decision tree returned 'archive' with no blocked reasons when
    tasks were done and no verify-report existed — recommending closing a change
    that was never verified, contradicting the proposal->...->verify->archive DAG.
    """
    _seed(tmp_path, "proposal.md", "specs/cap/spec.md", "design.md", "tasks.md")
    status = Resolve("demo", cwd=str(tmp_path))
    assert status.nextRecommended == "verify"
    assert status.nextRecommended != "archive"


def test_resolve_failing_verify_report_blocks_archive(tmp_path: Path) -> None:
    _seed(tmp_path, "proposal.md", "specs/cap/spec.md", "design.md", "tasks.md")
    (tmp_path / "openspec" / "changes" / "demo" / "verify-report.md").write_text(
        "verdict: FAIL\n", encoding="utf-8"
    )
    status = Resolve("demo", cwd=str(tmp_path))
    assert status.nextRecommended == "verify"


def test_resolve_passing_verify_report_routes_to_archive(tmp_path: Path) -> None:
    _seed(tmp_path, "proposal.md", "specs/cap/spec.md", "design.md", "tasks.md")
    (tmp_path / "openspec" / "changes" / "demo" / "verify-report.md").write_text(
        "verdict: PASS\n", encoding="utf-8"
    )
    assert Resolve("demo", cwd=str(tmp_path)).nextRecommended == "archive"


# ---------------------------------------------------------------------------
# REQ-OSS-003 — parse_verify_report verdict + unicode handling (T1.7)
# ---------------------------------------------------------------------------


def test_REQ_OSS_003_parse_verify_report_pass_clean(tmp_path: Path) -> None:
    """``verdict: PASS`` is allowed; no blocked reason added."""
    report = tmp_path / "verify-report.md"
    report.write_text("# verify report\n\nverdict: PASS\n", encoding="utf-8")

    verdict, reasons = parse_verify_report(report)
    assert verdict == "PASS"
    assert reasons == []


def test_REQ_OSS_003_parse_verify_report_fail_with_unicode_marks(
    tmp_path: Path,
) -> None:
    """A FAIL verdict (even with ``❌`` unicode marks) surfaces a blocked reason."""
    report = tmp_path / "verify-report.md"
    report.write_text(
        "# verify report\n\nverdict: FAIL\n\n"
        "## failures\n- ❌ tests/test_x.py::test_one\n- ❌ tests/test_x.py::test_two\n",
        encoding="utf-8",
    )

    verdict, reasons = parse_verify_report(report)
    assert verdict == "FAIL"
    assert reasons  # at least one failure surfaced
    assert all("❌" not in r for r in reasons)  # unicode stripped


def test_REQ_OSS_003_parse_verify_report_missing_verdict_field(tmp_path: Path) -> None:
    """A verify-report without a ``verdict:`` line is treated as missing."""
    report = tmp_path / "verify-report.md"
    report.write_text("# verify report\n\n(no verdict line)\n", encoding="utf-8")

    verdict, reasons = parse_verify_report(report)
    assert verdict == "missing"
    assert reasons == []


def test_REQ_OSS_003_resolve_fail_verdict_appears_in_blocked_reasons(
    tmp_path: Path,
) -> None:
    """A FAIL verify report ends up in ``Status.blockedReasons`` and
    drives ``nextRecommended = 'verify'``."""
    changes = tmp_path / "openspec" / "changes" / "demo"
    _write_minimal_change(changes)
    (changes / "design.md").write_text("# design\n", encoding="utf-8")
    (changes / "tasks.md").write_text("- [x] done\n", encoding="utf-8")
    (changes / "specs" / "demo-cap").mkdir(parents=True)
    (changes / "specs" / "demo-cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (changes / "verify-report.md").write_text("verdict: FAIL\n- ❌ test_one\n", encoding="utf-8")

    status = Resolve("demo", cwd=str(tmp_path))
    assert status.nextRecommended == "verify"
    assert any(r.startswith("verify_report:FAIL:") for r in status.blockedReasons)
