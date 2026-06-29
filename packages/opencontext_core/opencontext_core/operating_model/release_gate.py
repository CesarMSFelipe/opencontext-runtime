"""Release Definition-of-Done gate automation + the 1.0 acceptance verdict.

Two layers, both bound by build-rule #1 (HONESTY): every gate reports
``MET`` / ``NOT_MEASURED`` / ``FAILED`` truthfully. A check that cannot run
end-to-end from inside this process is ``NOT_MEASURED`` — never a fake pass — and
the 1.0 verdict is ``ready`` only when EVERY gate is genuinely ``MET``.

1. :class:`ReleaseGateRunner` — the four book §25 DoD regression gates (REL-11)
   computed as deltas against a stored baseline: no first-run regression, no
   benchmark-quality regression, no uncontrolled token increase, no critical
   policy bypass. The first run seeds the baseline and passes without blocking.

2. :class:`AcceptanceEvaluator` — the doc-57 final-1.0 gate set: A (the ten
   mandatory benchmark gates, via :class:`BenchmarkRunner`), B (the fifteen
   functional §10 behaviours), C (regression / non-negotiable), D (governance).
   It performs the two checks it CAN do honestly from here — the PyPI-token
   publish path and the versioned benchmark methodology stamp — and reports
   everything else as ``NOT_MEASURED`` unless measured evidence is injected.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.evaluation.models import GateStatus
from opencontext_core.evaluation.runner import (
    BenchmarkRunner,
    build_default_runner,
)
from opencontext_core.models.contract import VersionedContract

# ── Gate result + verdict contracts ──────────────────────────────────────────


class GateResult(BaseModel):
    """One acceptance/DoD gate's honest outcome."""

    model_config = ConfigDict(extra="forbid")

    gate: str = Field(description="Gate id, e.g. 'context-token-efficiency'.")
    category: str = Field(description="doc-57 category: A | B | C | D.")
    status: GateStatus
    detail: str = ""


class AcceptanceVerdict(VersionedContract):
    """Machine-readable 1.0 readiness verdict over A ∧ B ∧ C ∧ D (doc 57)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.acceptance_verdict.v1"
    ready: bool = Field(description="True only when every gate is MET.")
    methodology_version: str = Field(description="Versioned benchmark methodology stamp.")
    met: int = 0
    not_measured: int = 0
    failed: int = 0
    gates: list[GateResult] = Field(default_factory=list)

    @property
    def verdict(self) -> str:
        """Human verdict string: 'ready' or 'not-ready'."""
        return "ready" if self.ready else "not-ready"


# ── REL-11: the four DoD regression gates vs a stored baseline ───────────────


class ReleaseMetrics(BaseModel):
    """The measured release signals the four DoD gates compare across releases."""

    model_config = ConfigDict(extra="forbid")

    first_run_success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    benchmark_quality_score: float = Field(default=1.0, ge=0.0, le=1.0)
    median_tokens: int = Field(default=0, ge=0)
    critical_policy_bypasses: int = Field(default=0, ge=0)


class ReleaseBaselineStore:
    """Load/save the release-metrics baseline (atomic write, tolerant read).

    Mirrors ``quality/baseline.py`` exactly: a sibling temp file is written then
    ``os.replace``-d over the target so a reader never sees a partial file; a
    missing or corrupt file yields ``None`` so the gate seeds a fresh baseline
    rather than crashing.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> ReleaseMetrics | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return ReleaseMetrics.model_validate(data)
        except (OSError, ValueError):
            return None

    def save(self, metrics: ReleaseMetrics) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(metrics.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, self.path)


class ReleaseGateRunner:
    """Compute the four DoD regression gates as deltas vs a stored baseline."""

    def evaluate(
        self,
        current: ReleaseMetrics,
        baseline: ReleaseMetrics | None,
        *,
        token_threshold: float = 0.10,
    ) -> list[GateResult]:
        """Return the four DoD :class:`GateResult`s.

        First run (``baseline is None``) seeds and passes every gate without
        blocking (book §25 / REL-11 scenario). A critical policy bypass FAILS
        regardless of baseline (it is never acceptable).
        """
        if baseline is None:
            seeded = [
                self._gate("no-first-run-regression", GateStatus.MET, "baseline seeded"),
                self._gate("no-benchmark-quality-regression", GateStatus.MET, "baseline seeded"),
                self._gate("no-uncontrolled-token-increase", GateStatus.MET, "baseline seeded"),
            ]
            seeded.append(self._policy_gate(current))
            return seeded

        return [
            self._regression_gate(
                "no-first-run-regression",
                current.first_run_success_rate,
                baseline.first_run_success_rate,
                "first-run success rate",
            ),
            self._regression_gate(
                "no-benchmark-quality-regression",
                current.benchmark_quality_score,
                baseline.benchmark_quality_score,
                "benchmark quality score",
            ),
            self._token_gate(current, baseline, token_threshold),
            self._policy_gate(current),
        ]

    @staticmethod
    def _gate(name: str, status: GateStatus, detail: str) -> GateResult:
        return GateResult(gate=name, category="C", status=status, detail=detail)

    def _regression_gate(
        self, name: str, current: float, baseline: float, label: str
    ) -> GateResult:
        # A tiny epsilon absorbs float noise; any real drop below baseline blocks.
        if current + 1e-9 >= baseline:
            return self._gate(name, GateStatus.MET, f"{label} {current:.0%} >= base {baseline:.0%}")
        return self._gate(
            name, GateStatus.FAILED, f"{label} regressed: {current:.0%} < base {baseline:.0%}"
        )

    def _token_gate(
        self, current: ReleaseMetrics, baseline: ReleaseMetrics, threshold: float
    ) -> GateResult:
        name = "no-uncontrolled-token-increase"
        if baseline.median_tokens <= 0:
            return self._gate(name, GateStatus.MET, "no token baseline to compare")
        increase = (current.median_tokens - baseline.median_tokens) / baseline.median_tokens
        if increase <= threshold:
            return self._gate(
                name, GateStatus.MET, f"median tokens +{increase:.0%} <= threshold {threshold:.0%}"
            )
        return self._gate(
            name,
            GateStatus.FAILED,
            f"median tokens +{increase:.0%} exceeds threshold {threshold:.0%}",
        )

    def _policy_gate(self, current: ReleaseMetrics) -> GateResult:
        name = "no-critical-policy-bypass"
        if current.critical_policy_bypasses == 0:
            return self._gate(name, GateStatus.MET, "no critical policy bypass detected")
        return self._gate(
            name,
            GateStatus.FAILED,
            f"{current.critical_policy_bypasses} critical policy bypass(es) detected",
        )


# ── doc-57 final-1.0 acceptance verdict (A ∧ B ∧ C ∧ D) ──────────────────────

#: doc-57 §B — the fifteen functional 1.0 behaviours the run must do reliably.
FUNCTIONAL_BEHAVIOURS: tuple[str, ...] = (
    "create-usable-config",
    "detect-capabilities",
    "build-init-kg",
    "select-oc-flow-for-bugfix",
    "select-sdd-for-formal",
    "retrieve-minimal-context",
    "apply-small-mutation-safely",
    "run-local-inspection",
    "diagnose-bounded-failures",
    "escalate-when-needed",
    "persist-artifacts-receipts",
    "report-cost-confidence",
    "update-memory-kg-consolidation",
    "actionable-summary",
    "resume-if-interrupted",
)

#: doc-57 §D — governance gates.
GOVERNANCE_GATES: tuple[str, ...] = (
    "traceability-no-orphans",
    "receipts-reconstructable",
    "owner-resolution-hooks",
)

_StatusInput = GateStatus | tuple[GateStatus, str]

#: AVH-010 / B10 — the e2e Definition-of-Done proof artifact. The developer-journey
#: harness (tests/e2e) writes this when the full sequence
#: install -> doctor --strict -> index -> run --workflow auto -> pytest <golden> ->
#: release acceptance passes end-to-end; the mandatory ``e2e-dod`` gate reads it.
DOD_PROOF_PATH = ".opencontext/e2e/dod-proof.json"
DOD_PROOF_SCHEMA = "opencontext.e2e_dod_proof.v1"

#: The mandatory 1.0 gate id whose verdict is the hard, gating e2e DoD journey.
E2E_DOD_GATE = "e2e-dod"


def read_dod_proof(repo_root: Path) -> dict[str, Any] | None:
    """Read the e2e DoD proof artifact, or ``None`` when absent/unreadable."""
    path = Path(repo_root) / DOD_PROOF_PATH
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_dod_proof(repo_root: Path, *, passed: bool, steps: list[dict[str, Any]]) -> Path:
    """Persist the e2e DoD proof the ``e2e-dod`` gate reads (used by tests/e2e)."""
    path = Path(repo_root) / DOD_PROOF_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": DOD_PROOF_SCHEMA,
        "passed": bool(passed),
        "steps": steps,
        "generated_at": now_iso(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


@dataclass
class AcceptanceEvaluator:
    """Compose the doc-57 A∧B∧C∧D gate set into one honest verdict.

    ``repo_root`` is where the two self-checkable facts live (publish workflow).
    Inject ``functional`` / ``regression`` / ``governance`` mappings (gate →
    status or (status, detail)) to supply measured CI evidence; anything not
    injected stays honestly ``NOT_MEASURED``.
    """

    repo_root: Path = Path(".")
    runner: BenchmarkRunner | None = None

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)

    def evaluate(
        self,
        *,
        bench_root: str | Path = ".",
        smoke: bool = True,
        functional: Mapping[str, _StatusInput] | None = None,
        regression: Mapping[str, _StatusInput] | None = None,
        governance: Mapping[str, _StatusInput] | None = None,
        dod_gates: list[GateResult] | None = None,
        release_mode: bool = False,
        e2e_proof: Mapping[str, Any] | None = None,
    ) -> AcceptanceVerdict:
        runner = self.runner or build_default_runner()
        gates: list[GateResult] = []
        gates.extend(self._gate_a(runner, bench_root, smoke))
        gates.extend(self._gate_b(functional or {}))
        gates.extend(
            self._gate_c(
                runner, bench_root, smoke, regression or {}, dod_gates,
                release_mode=release_mode, e2e_proof=e2e_proof,
            )
        )
        gates.extend(self._gate_d(governance or {}))

        met = sum(1 for g in gates if g.status is GateStatus.MET)
        nm = sum(1 for g in gates if g.status is GateStatus.NOT_MEASURED)
        failed = sum(1 for g in gates if g.status is GateStatus.FAILED)
        return AcceptanceVerdict(
            ready=(met == len(gates) and len(gates) > 0),
            methodology_version=_methodology_version(runner, bench_root, smoke),
            met=met,
            not_measured=nm,
            failed=failed,
            gates=gates,
        )

    # -- A: the ten mandatory benchmark gates ---------------------------------
    def _gate_a(
        self, runner: BenchmarkRunner, bench_root: str | Path, smoke: bool
    ) -> list[GateResult]:
        out: list[GateResult] = []
        for report in runner.run_all(bench_root, smoke=smoke):
            out.append(
                GateResult(
                    gate=report.suite,
                    category="A",
                    status=report.status,
                    detail=report.notes or f"v{report.version}",
                )
            )
        return out

    # -- B: the fifteen functional behaviours ---------------------------------
    def _gate_b(self, functional: Mapping[str, _StatusInput]) -> list[GateResult]:
        return [
            _resolve(name, "B", functional, default_detail="no live functional run measured")
            for name in FUNCTIONAL_BEHAVIOURS
        ]

    # -- C: regression / non-negotiable ---------------------------------------
    def _gate_c(
        self,
        runner: BenchmarkRunner,
        bench_root: str | Path,
        smoke: bool,
        regression: Mapping[str, _StatusInput],
        dod_gates: list[GateResult] | None,
        *,
        release_mode: bool = False,
        e2e_proof: Mapping[str, Any] | None = None,
    ) -> list[GateResult]:
        out: list[GateResult] = []
        # Self-checkable here and now:
        out.append(self._publish_token_gate())
        out.append(self._methodology_versioned_gate(runner, bench_root, smoke))
        # AVH-010 / B10 — the HARD, gating e2e DoD journey.
        out.append(self._e2e_dod_gate(regression, release_mode=release_mode, e2e_proof=e2e_proof))
        # AVH-007 / B3 — per-subsystem parity-gated flip integrity (reads
        # .opencontext/flips/*.json; absent bundles add no gates).
        out.extend(self._flip_gates())
        # Externally measured (full suite / gate_k / mypy / ruff / forbidden-names):
        for name in (
            "suite-green",
            "gate-k-12-12",
            "mypy-strict-clean",
            "ruff-clean",
            "forbidden-names-clean",
        ):
            out.append(
                _resolve(name, "C", regression, default_detail="run in CI; not measured here")
            )
        # The four DoD baseline-delta gates (REL-11), if supplied.
        if dod_gates:
            out.extend(dod_gates)
        else:
            for name in (
                "no-first-run-regression",
                "no-benchmark-quality-regression",
                "no-uncontrolled-token-increase",
                "no-critical-policy-bypass",
            ):
                out.append(
                    GateResult(
                        gate=name,
                        category="C",
                        status=GateStatus.NOT_MEASURED,
                        detail="no release baseline supplied",
                    )
                )
        return out

    # -- D: governance --------------------------------------------------------
    def _gate_d(self, governance: Mapping[str, _StatusInput]) -> list[GateResult]:
        return [
            _resolve(name, "D", governance, default_detail="governance evidence not measured here")
            for name in GOVERNANCE_GATES
        ]

    # -- real, self-checkable C gates -----------------------------------------
    def _publish_token_gate(self) -> GateResult:
        """REAL check: publish.yml must use the PyPI API token, never OIDC.

        Recurring invalid-publisher break — this gate has genuine teeth.
        """
        name = "publish-uses-pypi-token-not-oidc"
        path = self.repo_root / ".github" / "workflows" / "publish.yml"
        if not path.is_file():
            return GateResult(
                gate=name,
                category="C",
                status=GateStatus.NOT_MEASURED,
                detail=f"{path} not found",
            )
        text = path.read_text(encoding="utf-8")
        has_token = "secrets.PYPI_API_TOKEN" in text
        # OIDC trusted publishing is signalled by an id-token permission.
        uses_oidc = "id-token: write" in text
        if has_token and not uses_oidc:
            return GateResult(
                gate=name, category="C", status=GateStatus.MET, detail="password: PYPI_API_TOKEN"
            )
        if uses_oidc:
            return GateResult(
                gate=name,
                category="C",
                status=GateStatus.FAILED,
                detail="OIDC (id-token: write) detected — must use secrets.PYPI_API_TOKEN",
            )
        return GateResult(
            gate=name,
            category="C",
            status=GateStatus.FAILED,
            detail="publish.yml does not reference secrets.PYPI_API_TOKEN",
        )

    def _e2e_dod_gate(
        self,
        regression: Mapping[str, _StatusInput],
        *,
        release_mode: bool,
        e2e_proof: Mapping[str, Any] | None,
    ) -> GateResult:
        """The mandatory e2e Definition-of-Done gate (AVH-010 / B10).

        The DoD journey (``install -> doctor --strict -> index -> run --workflow auto
        -> pytest <golden> -> release acceptance``) is the HARD 1.0 acceptance gate:
        1.0 CANNOT be declared unless it is ``MET``.

        * Explicitly injected evidence (``regression['e2e-dod']``) wins (test path).
        * A proof artifact (injected ``e2e_proof`` or ``<root>/.opencontext/e2e/
          dod-proof.json``) with ``passed: true`` → ``MET``.
        * Otherwise: in RELEASE mode an unproven sequence is ``FAILED`` (never
          ``NOT_MEASURED``) so it gates the release; in dev mode it is honestly
          ``NOT_MEASURED`` (not run here).
        """
        name = E2E_DOD_GATE
        if name in regression:
            return _resolve(name, "C", regression, default_detail="")
        proof = e2e_proof if e2e_proof is not None else read_dod_proof(self.repo_root)
        if proof is not None and bool(proof.get("passed")):
            steps = proof.get("steps") or []
            return GateResult(
                gate=name, category="C", status=GateStatus.MET,
                detail=f"DoD e2e sequence proven end-to-end ({len(steps)} steps passed)",
            )
        if release_mode:
            return GateResult(
                gate=name, category="C", status=GateStatus.FAILED,
                detail="DoD e2e sequence unproven — 1.0 cannot be declared (run tests/e2e)",
            )
        return GateResult(
            gate=name, category="C", status=GateStatus.NOT_MEASURED,
            detail="DoD e2e sequence not proven in this environment (run tests/e2e)",
        )

    def _flip_gates(self) -> list[GateResult]:
        """One integrity gate per recorded vNext flip (AVH-007 / B3).

        Reads ``.opencontext/flips/*.json`` under ``repo_root``. A flag counts as
        flipped for release ONLY behind a complete, accepted bundle whose recorded
        config matches the ACTIVE flag state:

        * bundle missing one of the four artifacts -> ``FAILED`` (rejected, missing
          artifact named);
        * ACTIVE flag != the bundle's recorded config -> ``FAILED`` (mismatch named);
        * accepted bundle, ACTIVE == ``config_after`` -> ``MET``;
        * auto-reverted bundle, ACTIVE == legacy ``config_before`` -> ``MET`` (an honest
          revert is not a release failure — a partial flip set is a valid outcome).

        Absent bundles add no gates, so a fresh checkout / CI run is unaffected.
        """
        from opencontext_core.compat.flip_evidence import active_flag_value, read_flip_bundles

        gates: list[GateResult] = []
        for bundle in read_flip_bundles(self.repo_root):
            name = f"flip-{bundle.subsystem}"
            missing = bundle.missing_artifacts()
            if missing:
                gates.append(
                    GateResult(
                        gate=name, category="C", status=GateStatus.FAILED,
                        detail=f"flip bundle incomplete — missing: {', '.join(missing)}",
                    )
                )
                continue
            active = active_flag_value(bundle.flag)
            expected = bundle.expected_active()
            if active != expected:
                where = "config_after" if bundle.accepted else "config_before (reverted)"
                gates.append(
                    GateResult(
                        gate=name, category="C", status=GateStatus.FAILED,
                        detail=f"ACTIVE {bundle.flag}={active!r} != {where} {expected!r}",
                    )
                )
                continue
            if bundle.accepted:
                detail = f"flip accepted; ACTIVE {bundle.flag}={active!r} matches config_after"
            else:
                detail = (
                    f"auto-reverted; ACTIVE {bundle.flag}={active!r} is legacy default "
                    f"({bundle.reason})"
                )
            gates.append(GateResult(gate=name, category="C", status=GateStatus.MET, detail=detail))
        return gates

    def _methodology_versioned_gate(
        self, runner: BenchmarkRunner, bench_root: str | Path, smoke: bool
    ) -> GateResult:
        """REAL check: every benchmark report carries a suite + semver version."""
        name = "benchmark-methodology-versioned"
        reports = runner.run_all(bench_root, smoke=smoke)
        unstamped = [r.suite for r in reports if not r.suite or not r.version]
        if unstamped:
            return GateResult(
                gate=name,
                category="C",
                status=GateStatus.FAILED,
                detail=f"unstamped reports: {', '.join(unstamped)}",
            )
        return GateResult(
            gate=name,
            category="C",
            status=GateStatus.MET,
            detail=f"{len(reports)} suites stamped suite+version",
        )


def _methodology_version(runner: BenchmarkRunner, bench_root: str | Path, smoke: bool) -> str:
    reports = runner.run_all(bench_root, smoke=smoke)
    versions = {r.version for r in reports if r.version}
    return sorted(versions)[0] if versions else "0"


def _resolve(
    name: str, category: str, source: Mapping[str, _StatusInput], *, default_detail: str
) -> GateResult:
    if name in source:
        value = source[name]
        if isinstance(value, tuple):
            status, detail = value
        else:
            status, detail = value, "measured"
        return GateResult(gate=name, category=category, status=status, detail=detail)
    return GateResult(
        gate=name, category=category, status=GateStatus.NOT_MEASURED, detail=default_detail
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "DOD_PROOF_PATH",
    "E2E_DOD_GATE",
    "FUNCTIONAL_BEHAVIOURS",
    "GOVERNANCE_GATES",
    "AcceptanceEvaluator",
    "AcceptanceVerdict",
    "GateResult",
    "ReleaseBaselineStore",
    "ReleaseGateRunner",
    "ReleaseMetrics",
    "now_iso",
    "read_dod_proof",
    "write_dod_proof",
]
