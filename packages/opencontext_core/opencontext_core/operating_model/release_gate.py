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
    ready: bool = Field(
        description=(
            "True only when every non-deferred gate is MET (deferred provider-CI gates "
            "that are NOT_MEASURED do not block; see DEFERRED_PROVIDER_CI_GATES)."
        )
    )
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
    "wrong-edit-not-completed",
    "secret-edit-rolled-back",
    "provider-error-redacted",
    "pyz-artifact-smoke",
)

#: doc-57 §D — governance gates.
GOVERNANCE_GATES: tuple[str, ...] = (
    "receipts-reconstructable",
    "owner-resolution-hooks",
)

#: B4 — §A suite name → list of §B functional behaviour gate ids that the suite
#: exercises.  When a suite is MET, the corresponding functional behaviours are
#: inferred as MET; when FAILED, they are inferred as FAILED.  Behaviours that
#: require a live e2e journey (no suite covers them) are left NOT_MEASURED.
#:
#: Mapping rationale:
#:   first-run           → create-usable-config (first run creates a config file),
#:                          detect-capabilities  (doctor call detects installed caps)
#:   oc-flow-bugfix      → select-oc-flow-for-bugfix (OC-flow is selected for the task),
#:                          apply-small-mutation-safely (ApplyEdit patches the file)
#:   sdd-formal-feature  → select-sdd-for-formal (SDD route is selected)
#:   memory-usefulness   → update-memory-kg-consolidation (memory save+search roundtrip)
#:   policy-security     → run-local-inspection (policy engine = local behaviour inspection)
#:   provider-fallback   → diagnose-bounded-failures (provider error = bounded, handled)
#:   resume-rollback     → resume-if-interrupted (checkpoint resume = interrupted recovery)
SUITE_TO_FUNCTIONAL: dict[str, list[str]] = {
    "first-run": ["create-usable-config", "detect-capabilities"],
    "oc-flow-localized-bugfix": ["select-oc-flow-for-bugfix", "apply-small-mutation-safely"],
    "sdd-formal-feature": ["select-sdd-for-formal"],
    "memory-usefulness": ["update-memory-kg-consolidation"],
    "policy-security": ["run-local-inspection"],
    "provider-fallback": ["diagnose-bounded-failures"],
    "resume-rollback": ["resume-if-interrupted"],
}

_StatusInput = GateStatus | tuple[GateStatus, str]

#: AVH-010 / B10 — the e2e Definition-of-Done proof artifact. The developer-journey
#: harness (tests/e2e) writes this when the full sequence
#: install -> doctor --strict -> index -> run --workflow auto -> pytest <golden> ->
#: release acceptance passes end-to-end; the mandatory ``e2e-dod`` gate reads it.
DOD_PROOF_PATH = ".opencontext/e2e/dod-proof.json"
DOD_PROOF_SCHEMA = "opencontext.e2e_dod_proof.v1"

#: The mandatory 1.0 gate id whose verdict is the hard, gating e2e DoD journey.
E2E_DOD_GATE = "e2e-dod"

#: VDM-007 / B+D — the e2e developer journey writes this single evidence artifact
#: capturing the 15 functional (B) + 2 governance (D) gate outcomes from a real
#: init -> doctor -> index -> run -> session journey. ``release acceptance`` reads it
#: and injects ``functional=`` / ``governance=``. A separate path from the package
#: ``release evidence`` output to avoid a name collision.
RELEASE_EVIDENCE_PATH = ".opencontext/e2e/release-evidence.json"
RELEASE_EVIDENCE_SCHEMA = "opencontext.release_evidence.v1"

#: VDM-006 — the CI workflow writes a ``{gate: bool}`` map for the five externally
#: measured regression gates; ``release acceptance`` reads it as the ``regression=``
#: evidence source. Absent file -> those gates stay honestly NOT_MEASURED.
CI_GATES_PATH = ".opencontext/reports/ci-gates.json"

#: VDM-008 / Option A — the two A-gates that require a live provider (embeddings /
#: real context builds). They ship runner hooks but stay NOT_MEASURED in provider-free
#: CI; their NOT_MEASURED status MUST NOT drive ``ready=False`` (deferral is recorded in
#: ``DEFERRED_PROVIDER_CI.md``). A FAILED verdict (real, not deferral) still blocks.
DEFERRED_PROVIDER_CI_GATES: tuple[str, ...] = (
    "kg-retrieval-precision",
    "context-token-efficiency",
)


def _status_input_from(value: Any) -> _StatusInput | None:
    """Convert a JSON-friendly evidence value into a gate-status input.

    Accepts ``bool`` (True->MET / False->FAILED), a status string (``"met"`` /
    ``"failed"`` / ``"not-measured"``, tolerant of underscores and pass/fail aliases),
    or a ``[status, detail]`` pair. Returns ``None`` for an unparseable value so the
    caller can drop it and leave the gate honestly NOT_MEASURED.
    """
    detail = ""
    raw: Any = value
    if isinstance(value, (list, tuple)) and len(value) == 2:
        raw, detail = value[0], str(value[1])
    if isinstance(raw, bool):
        status: GateStatus | None = GateStatus.MET if raw else GateStatus.FAILED
    elif isinstance(raw, str):
        alias = {
            "met": GateStatus.MET,
            "pass": GateStatus.MET,
            "passed": GateStatus.MET,
            "ok": GateStatus.MET,
            "failed": GateStatus.FAILED,
            "fail": GateStatus.FAILED,
            "not-measured": GateStatus.NOT_MEASURED,
            "not_measured": GateStatus.NOT_MEASURED,
        }
        status = alias.get(raw.strip().lower().replace("_", "-"))
        if status is None:
            status = alias.get(raw.strip().lower())
    else:
        status = None
    if status is None:
        return None
    return (status, detail) if detail else status


def _load_status_map(path: Path) -> dict[str, _StatusInput]:
    """Read a ``{gate: status}`` JSON map into a gate -> status-input mapping.

    A missing/unreadable file yields ``{}`` (not an error); an unparseable entry is
    dropped so the corresponding gate stays honestly NOT_MEASURED.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, _StatusInput] = {}
    for gate, value in data.items():
        parsed = _status_input_from(value)
        if parsed is not None:
            out[str(gate)] = parsed
    return out


def read_ci_gates(repo_root: Path, *, path: str = CI_GATES_PATH) -> dict[str, _StatusInput]:
    """Read the CI regression-gate evidence map written by release-acceptance.yml.

    Returns a ``{gate: status}`` mapping suitable for the ``regression=`` parameter of
    :meth:`AcceptanceEvaluator.evaluate`. Absent file -> ``{}`` so the five CI gates
    stay NOT_MEASURED (honest), never a fabricated pass.
    """
    return _load_status_map(Path(repo_root) / path)


def read_release_evidence(
    repo_root: Path, *, path: str = RELEASE_EVIDENCE_PATH
) -> tuple[dict[str, _StatusInput], dict[str, _StatusInput]]:
    """Read the e2e B+D evidence artifact -> ``(functional, governance)`` maps.

    The artifact shape is ``{"functional": {gate: status}, "governance": {gate: status}}``.
    A missing/unreadable file yields ``({}, {})`` (not an error) so every B and D gate
    stays honestly NOT_MEASURED until a real journey supplies evidence (VDM-007).
    """
    file = Path(repo_root) / path
    if not file.is_file():
        return {}, {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}

    def _coerce(section: Any) -> dict[str, _StatusInput]:
        out: dict[str, _StatusInput] = {}
        if isinstance(section, dict):
            for gate, value in section.items():
                parsed = _status_input_from(value)
                if parsed is not None:
                    out[str(gate)] = parsed
        return out

    return _coerce(data.get("functional")), _coerce(data.get("governance"))


def write_release_evidence(
    repo_root: Path,
    *,
    functional: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> Path:
    """Persist the B+D evidence artifact the acceptance evaluator reads (used by tests/e2e)."""
    path = Path(repo_root) / RELEASE_EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": RELEASE_EVIDENCE_SCHEMA,
        "functional": dict(functional),
        "governance": dict(governance),
        "generated_at": now_iso(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


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

        # Run §A suites once; reuse for both A-gate scoring and B-gate derivation.
        suite_reports = list(runner.run_all(bench_root, smoke=smoke))

        # Derive functional evidence from §A suite results, then merge with any
        # explicitly injected evidence (injected values take precedence).
        derived = self._derive_functional_from_suites(suite_reports)
        merged_functional: dict[str, _StatusInput] = {**derived, **(functional or {})}

        gates: list[GateResult] = []
        gates.extend(self._gate_a_from_reports(suite_reports))
        gates.extend(self._gate_b(merged_functional))
        gates.extend(
            self._gate_c(
                runner,
                bench_root,
                smoke,
                regression or {},
                dod_gates,
                release_mode=release_mode,
                e2e_proof=e2e_proof,
                suite_reports=suite_reports,
            )
        )
        gates.extend(self._gate_d(governance or {}))

        # VDM-008 / Option A: a deferred provider-CI gate that is NOT_MEASURED does not
        # block readiness (its deferral is documented in DEFERRED_PROVIDER_CI.md); we
        # annotate it and exclude it from the ready denominator. A deferred gate that
        # is FAILED (a real failure, not a deferral) still blocks.
        for gate in gates:
            if gate.gate in DEFERRED_PROVIDER_CI_GATES and gate.status is GateStatus.NOT_MEASURED:
                gate.detail = (gate.detail + "; " if gate.detail else "") + (
                    "DEFERRED provider-CI gate (Option A) — does not block ready; "
                    "see DEFERRED_PROVIDER_CI.md"
                )

        met = sum(1 for g in gates if g.status is GateStatus.MET)
        nm = sum(1 for g in gates if g.status is GateStatus.NOT_MEASURED)
        failed = sum(1 for g in gates if g.status is GateStatus.FAILED)
        blocking = [
            g
            for g in gates
            if not (g.gate in DEFERRED_PROVIDER_CI_GATES and g.status is GateStatus.NOT_MEASURED)
        ]
        ready = bool(blocking) and all(g.status is GateStatus.MET for g in blocking)
        return AcceptanceVerdict(
            ready=ready,
            methodology_version=_methodology_version(runner, bench_root, smoke, suite_reports),
            met=met,
            not_measured=nm,
            failed=failed,
            gates=gates,
        )

    # -- A: the ten mandatory benchmark gates ---------------------------------
    def _gate_a_from_reports(
        self, suite_reports: list[Any]
    ) -> list[GateResult]:
        """Translate pre-run suite reports into §A gate results."""
        out: list[GateResult] = []
        for report in suite_reports:
            out.append(
                GateResult(
                    gate=report.suite,
                    category="A",
                    status=report.status,
                    detail=report.notes or f"v{report.version}",
                )
            )
        return out

    # B4 helper — derive §B functional evidence from §A suite outcomes.
    def _derive_functional_from_suites(
        self, suite_reports: list[Any]
    ) -> dict[str, _StatusInput]:
        """Map §A suite results to §B functional behaviour gate evidence.

        Only suites listed in ``SUITE_TO_FUNCTIONAL`` contribute evidence.
        A MET suite → the mapped behaviours become MET; a FAILED suite → FAILED.
        NOT_MEASURED suites contribute nothing (the behaviour stays NOT_MEASURED
        unless explicit evidence is injected or another suite covers it).

        Injected evidence in ``evaluate()`` always takes precedence over derived
        evidence (the caller passes injected values after merging with this output).
        """
        derived: dict[str, _StatusInput] = {}
        for report in suite_reports:
            suite_name: str = report.suite
            if suite_name not in SUITE_TO_FUNCTIONAL:
                continue
            if report.status is GateStatus.NOT_MEASURED:
                # Cannot derive evidence from a deferred / unmeasured suite.
                continue
            behaviours = SUITE_TO_FUNCTIONAL[suite_name]
            detail = f"derived from {suite_name} suite ({report.notes or 'v' + report.version})"
            status = report.status  # MET or FAILED — both are honest evidence
            for behaviour in behaviours:
                # First-writer wins; if two suites map to the same behaviour,
                # take the first one (deterministic: MANDATORY_GATES order).
                if behaviour not in derived:
                    derived[behaviour] = (status, detail)
        return derived

    # -- B: the fifteen functional behaviours ---------------------------------
    def _gate_b(self, functional: Mapping[str, _StatusInput]) -> list[GateResult]:
        out: list[GateResult] = []
        for name in FUNCTIONAL_BEHAVIOURS:
            if name == "pyz-artifact-smoke" and name not in functional:
                # Self-checkable: verify that the release .pyz artifact exists
                # under dist/ or at the repo root (built by the publish pipeline).
                out.append(self._pyz_artifact_gate())
            else:
                out.append(
                    _resolve(
                        name, "B", functional, default_detail="no live functional run measured"
                    )
                )
        return out

    def _pyz_artifact_gate(self) -> GateResult:
        """REAL check: opencontext.pyz release artifact must exist in dist/."""
        name = "pyz-artifact-smoke"
        # Check dist/ first, then repo root (some pipelines write it at root).
        for candidate in (
            self.repo_root / "dist" / "opencontext.pyz",
            self.repo_root / "opencontext.pyz",
        ):
            if candidate.is_file():
                return GateResult(
                    gate=name,
                    category="B",
                    status=GateStatus.MET,
                    detail=f"opencontext.pyz found at {candidate.relative_to(self.repo_root)}",
                )
        return GateResult(
            gate=name,
            category="B",
            status=GateStatus.NOT_MEASURED,
            detail="opencontext.pyz not found in dist/ or repo root — build pipeline pending",
        )

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
        suite_reports: list[Any] | None = None,
    ) -> list[GateResult]:
        out: list[GateResult] = []
        # Self-checkable here and now:
        out.append(self._publish_token_gate())
        out.append(self._methodology_versioned_gate(runner, bench_root, smoke, suite_reports))
        # AVH-010 / B10 — the HARD, gating e2e DoD journey.
        out.append(self._e2e_dod_gate(regression, release_mode=release_mode, e2e_proof=e2e_proof))
        # AVH-007 / B3 — per-subsystem parity-gated flip integrity (reads
        # .opencontext/flips/*.json; absent bundles add no gates). The flip gate is
        # computed honestly from the ACTIVE flag default vs the recorded bundle; the
        # ACTIVE default for the spine flags derives from the migration ledger
        # (compat/flags), so a correct post-C15 state computes MET with no injection.
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
                gate=name,
                category="C",
                status=GateStatus.MET,
                detail=f"DoD e2e sequence proven end-to-end ({len(steps)} steps passed)",
            )
        if release_mode:
            return GateResult(
                gate=name,
                category="C",
                status=GateStatus.FAILED,
                detail="DoD e2e sequence unproven — 1.0 cannot be declared (run tests/e2e)",
            )
        return GateResult(
            gate=name,
            category="C",
            status=GateStatus.NOT_MEASURED,
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
                        gate=name,
                        category="C",
                        status=GateStatus.FAILED,
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
                        gate=name,
                        category="C",
                        status=GateStatus.FAILED,
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
        self,
        runner: BenchmarkRunner,
        bench_root: str | Path,
        smoke: bool,
        suite_reports: list[Any] | None = None,
    ) -> GateResult:
        """REAL check: every benchmark report carries a suite + semver version."""
        name = "benchmark-methodology-versioned"
        # Re-use pre-run reports when available to avoid a second full run.
        reports = (
            suite_reports
            if suite_reports is not None
            else list(runner.run_all(bench_root, smoke=smoke))
        )
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


def _methodology_version(
    runner: BenchmarkRunner,
    bench_root: str | Path,
    smoke: bool,
    suite_reports: list[Any] | None = None,
) -> str:
    reports = (
        suite_reports
        if suite_reports is not None
        else list(runner.run_all(bench_root, smoke=smoke))
    )
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
    "CI_GATES_PATH",
    "DEFERRED_PROVIDER_CI_GATES",
    "DOD_PROOF_PATH",
    "E2E_DOD_GATE",
    "FUNCTIONAL_BEHAVIOURS",
    "GOVERNANCE_GATES",
    "RELEASE_EVIDENCE_PATH",
    "SUITE_TO_FUNCTIONAL",
    "AcceptanceEvaluator",
    "AcceptanceVerdict",
    "GateResult",
    "ReleaseBaselineStore",
    "ReleaseGateRunner",
    "ReleaseMetrics",
    "now_iso",
    "read_ci_gates",
    "read_dod_proof",
    "read_release_evidence",
    "write_dod_proof",
    "write_release_evidence",
]
