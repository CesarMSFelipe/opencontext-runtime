"""`opencontext sdd review` — honest structural review over change artifacts + diff.

Contract: the verb reviews the change's artifacts (same disk truth as `sdd status`)
plus the working-tree diff footprint, persists `review-report.json` (and a
`review.md` rendered through the shared review machinery) in the change dir, and
never fabricates model findings — without an executor/model the report is marked
``mode: structural``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from opencontext_cli.commands.sdd_cmd import SUBCOMMANDS, add_sdd_parser, handle_sdd


def _build_parent() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opencontext")
    sub = parser.add_subparsers(dest="command", required=True)
    add_sdd_parser(sub)
    return parser


def _seed_change(root: Path, name: str = "demo-change", *, verify_pass: bool = True) -> Path:
    """A change dir as a completed SDD cycle leaves it (proposal → verify)."""
    change = root / "openspec" / "changes" / name
    (change / "specs" / "core").mkdir(parents=True)
    (change / "proposal.md").write_text("# Proposal: demo\n", encoding="utf-8")
    (change / "specs" / "core" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (change / "design.md").write_text("# Design\n", encoding="utf-8")
    (change / "tasks.md").write_text("- [x] T1 do the thing\n", encoding="utf-8")
    if verify_pass:
        (change / "verify-report.md").write_text("verdict: PASS\n", encoding="utf-8")
    return change


def _run_review(root: Path, change: str, capsys: pytest.CaptureFixture) -> dict:
    parser = _build_parent()
    args = parser.parse_args(["sdd", "review", change, "--cwd", str(root), "--json"])
    handle_sdd(args)
    return json.loads(capsys.readouterr().out)


def test_sdd_review_verb_registered() -> None:
    assert "review" in SUBCOMMANDS
    parser = _build_parent()
    args = parser.parse_args(["sdd", "review", "--change", "demo", "--cwd", ".", "--json"])
    assert args.sdd_command == "review"
    assert args.change == "demo"


def test_sdd_review_writes_report_and_envelope(tmp_path: Path, capsys) -> None:
    change_dir = _seed_change(tmp_path)
    out = _run_review(tmp_path, "demo-change", capsys)

    # Canonical PhaseResultEnvelope fields.
    assert out["status"] == "ok"
    assert out["phase"] == "review"
    assert out["next_recommended"] == "archive"
    assert "review-report" in out["artifacts"]

    report_path = change_dir / "review-report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schemaName"] == "opencontext.sdd-review"
    assert report["schemaVersion"] == 1
    assert report["change"] == "demo-change"
    # Honest: no executor/model configured — static checks only, no fabrication.
    assert report["mode"] == "structural"
    assert report["findings"] == []
    assert "diff" in report

    # Human-readable companion rendered through the shared review machinery.
    assert (change_dir / "review.md").is_file()


def test_sdd_review_flags_incomplete_artifacts(tmp_path: Path, capsys) -> None:
    change = tmp_path / "openspec" / "changes" / "young-change"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text("# Proposal\n", encoding="utf-8")

    out = _run_review(tmp_path, "young-change", capsys)

    assert out["status"] == "ok"
    assert out["risks"], "missing artifacts must surface as risks"
    report = json.loads((change / "review-report.json").read_text(encoding="utf-8"))
    titles = " ".join(f["title"] for f in report["findings"])
    assert "design" in titles
    assert "tasks" in titles


def test_sdd_review_blocked_when_change_missing(tmp_path: Path, capsys) -> None:
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    parser = _build_parent()
    args = parser.parse_args(["sdd", "review", "ghost", "--cwd", str(tmp_path), "--json"])

    with pytest.raises(SystemExit) as exc:
        handle_sdd(args)

    assert exc.value.code == 7  # SDD_ARTIFACTS_MISSING
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "blocked"
    assert out["exit_code"] == 7
    assert not (tmp_path / "openspec" / "changes" / "ghost").exists()


def test_sdd_review_updates_cycle_state_in_status(tmp_path: Path, capsys) -> None:
    _seed_change(tmp_path)
    _run_review(tmp_path, "demo-change", capsys)

    from opencontext_sdd.status import Resolve

    status = Resolve("demo-change", cwd=str(tmp_path))
    assert status.artifacts.get("review-report") == "done"
    assert status.artifactPaths.get("review-report", "").endswith("review-report.json")
