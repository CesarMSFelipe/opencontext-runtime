"""Archive gate — enforces that all phase evidence is present before archiving."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar


class OcNewArchiveGate:
    REQUIRED: ClassVar[list[str]] = [
        "explore.artifact.json",
        "propose.artifact.json",
        "spec.artifact.json",
        "design.artifact.json",
        "tasks.artifact.json",
        "approval.json",
        "apply-manifest.json",
        "verify-report.json",
        "review-report.json",
        "compliance-matrix.json",
        "harness-report.json",
    ]

    def validate(self, run_dir: Path) -> list[str]:
        return [name for name in self.REQUIRED if not (run_dir / name).exists()]

    def _check_verify_report(self, run_dir: Path) -> str | None:
        """Returns failure reason or None if passing."""
        path = run_dir / "verify-report.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"verify-report.json unparseable: {e}"
        verdict = data.get("verdict") or data.get("passed")
        if verdict in ("PASS", True):
            return None
        return f"verify-report.json verdict={verdict!r}"

    def _check_compliance_matrix(self, run_dir: Path) -> str | None:
        path = run_dir / "compliance-matrix.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"compliance-matrix.json unparseable: {e}"
        if data.get("passed") is True:
            return None
        return f"compliance-matrix.json passed={data.get('passed')!r}"

    def _check_harness_report(self, run_dir: Path) -> str | None:
        path = run_dir / "harness-report.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"harness-report.json unparseable: {e}"
        if data.get("passed") is True:
            return None
        failures = data.get("failures", [])
        return f"harness-report.json passed=False failures={failures}"

    def assert_can_archive(self, run_dir: Path) -> None:
        missing = self.validate(run_dir)
        if missing:
            raise RuntimeError("Cannot archive; missing: " + ", ".join(missing))

        # Semantic content validation
        content_failures: list[str] = []
        for check in (
            self._check_verify_report,
            self._check_compliance_matrix,
            self._check_harness_report,
        ):
            reason = check(run_dir)
            if reason is not None:
                content_failures.append(reason)

        if content_failures:
            raise RuntimeError("Cannot archive; content failures: " + "; ".join(content_failures))
