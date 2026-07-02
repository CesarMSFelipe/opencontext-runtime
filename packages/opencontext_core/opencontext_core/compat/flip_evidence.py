"""Flip evidence bundle — gate each vNext default flip on recorded evidence (AVH-007 / B3).

A vNext subsystem flag flips to default-on ONLY behind a complete, accepted evidence
bundle. Each bundle records the four artifacts the spec mandates:

    (1) config before/after snapshot   -- the flag value either side of the flip
    (2) before/after benchmark record  -- the relevant golden/benchmark verdicts + the
                                          targeted-test pass/fail counts
    (3) parity result                  -- ``compat/parity.check_parity`` (legacy vs vNext)
    (4) rollback handle                -- the flag + restore path that reverts the flip

A flip is ACCEPTED only when all four artifacts are present AND parity passed AND the
after-benchmark is not worse than the before-benchmark. Otherwise it is AUTO-REVERTED:
the flag default stays off and the bundle records ``reverted=True`` with the reason. The
mechanism NEVER forces a flip — a failing parity or a regressed benchmark always reverts.

Bundles are written to ``.opencontext/flips/<subsystem>.json`` (gitignored runtime
artifacts) and read back by :class:`operating_model.release_gate.AcceptanceEvaluator`,
which rejects any bundle missing one of the four artifacts and verifies that the ACTIVE
flag state matches the bundle's recorded config (``config_after`` when accepted, the
legacy ``config_before`` when reverted).

This module imports only ``compat.parity`` (+ a lazy ``compat.flags`` read) and the
standard library, so ``release_gate`` can import it without a cycle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat.parity import ParityReport

#: Directory (under the repo/project root) holding per-subsystem flip bundles. This is
#: gitignored runtime churn (every ``release acceptance`` run may rewrite it).
FLIPS_DIR = ".opencontext/flips"

#: Tracked, committed baseline of ACCEPTED flip bundles. Unlike :data:`FLIPS_DIR` this
#: path is NOT gitignored, so the migration evidence is reproducible on a fresh CI
#: checkout. :func:`read_flip_bundles` reads the union of this baseline and the runtime
#: dir, with the runtime path winning on a per-subsystem conflict.
FLIP_BASELINE_DIR = "tests/compat/flip_baseline"

#: Bundle schema version (bump on any field change so old bundles are diffable).
FLIP_SCHEMA_VERSION = 1

#: The four mandatory artifacts every accepted bundle must carry (spec AVH-007).
REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "config snapshot",
    "benchmark record",
    "parity result",
    "rollback flag",
)

#: Honest ordering so "benchmark not worse" is well-defined (FAILED < NOT_MEASURED < MET).
_STATUS_RANK: dict[str, int] = {"failed": 0, "not-measured": 1, "met": 2}

#: The documented, parity-gated flip order keyed by subsystem (tasks.md 8.1 / AUDIT B3).
#: Earlier subsystems flip before later ones; the advisory pair (runtime_brain,
#: runtime_intelligence) is attempted last under the same gating. Each flip is decided
#: independently on its own parity/benchmark evidence, but an ACCEPTED flip may not skip
#: an earlier, un-accepted subsystem in this order (see :func:`sequence_violation`).
FLIP_SEQUENCE: tuple[str, ...] = (
    "workflow_registry",  # runtime.registry_enabled
    "artifact_store",  # runtime.durable_artifacts
    "oc_flow",  # runtime.oc_flow_enabled
    "context_engine",  # runtime.context_engine_enabled
    "knowledge_graph",  # runtime.kg_v2_enabled
    "memory",  # runtime.memory_v2_enabled
    "provider_gateway",  # runtime.gateway_enabled
    "persona_registry",  # runtime.persona_registry_enabled
    "skill_registry",  # runtime.skill_registry_enabled
    "harness_registry",  # runtime.harness_registry_enabled
    "rt_spine",  # runtime.rt-spine (Phase-2 spine — RuntimeApi default route)
    "mcp_runtime",  # runtime.mcp-runtime (Phase-2 MCP session dispatcher)
    "runtime_brain",  # runtime_brain.enabled (advisory)
    "runtime_intelligence",  # runtime_intelligence_enabled (advisory)
)

#: Subsystem -> dotted config flag, for the documented flip sequence.
SUBSYSTEM_FLAGS: dict[str, str] = {
    "workflow_registry": "runtime.registry_enabled",
    "artifact_store": "runtime.durable_artifacts",
    "oc_flow": "runtime.oc_flow_enabled",
    "context_engine": "runtime.context_engine_enabled",
    "knowledge_graph": "runtime.kg_v2_enabled",
    "memory": "runtime.memory_v2_enabled",
    "provider_gateway": "runtime.gateway_enabled",
    "persona_registry": "runtime.persona_registry_enabled",
    "skill_registry": "runtime.skill_registry_enabled",
    "harness_registry": "runtime.harness_registry_enabled",
    "rt_spine": "runtime.rt-spine",
    "mcp_runtime": "runtime.mcp-runtime",
    "runtime_brain": "runtime_brain.enabled",
    "runtime_intelligence": "runtime_intelligence_enabled",
}


def sequence_violation(accepted_subsystems: list[str] | set[str]) -> str | None:
    """Return a violation message if accepted flips skip the documented order, else ``None``.

    Accepted flips MUST form a prefix of :data:`FLIP_SEQUENCE`: a later subsystem may be
    accepted only when every earlier subsystem in the order is also accepted. An empty
    accepted set (the honest all-reverted outcome) never violates the order.
    """
    accepted = set(accepted_subsystems)
    unknown = accepted - set(FLIP_SEQUENCE)
    if unknown:
        return f"unknown subsystem(s) not in the documented flip order: {sorted(unknown)}"
    seen_gap = False
    for subsystem in FLIP_SEQUENCE:
        if subsystem in accepted:
            if seen_gap:
                return (
                    f"out-of-sequence flip: '{subsystem}' accepted before an earlier "
                    f"subsystem in the documented order"
                )
        else:
            seen_gap = True
    return None


class FlipEvidence(BaseModel):
    """One subsystem's parity-gated default-flip evidence bundle (versioned artifact)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = FLIP_SCHEMA_VERSION
    subsystem: str
    flag: str = Field(description="Dotted config flag, e.g. 'runtime.registry_enabled'.")
    config_before: dict[str, Any] = Field(default_factory=dict)
    config_after: dict[str, Any] = Field(default_factory=dict)
    benchmark_before: dict[str, Any] = Field(default_factory=dict)
    benchmark_after: dict[str, Any] = Field(default_factory=dict)
    parity: dict[str, Any] = Field(default_factory=dict)
    rollback_flag: str = ""
    rollback_path: str = ""
    accepted: bool = False
    reverted: bool = False
    reason: str = ""
    generated_at: str = ""

    def missing_artifacts(self) -> list[str]:
        """Return the names of any of the four mandatory artifacts that are absent."""
        missing: list[str] = []
        if not self.config_before or not self.config_after:
            missing.append("config snapshot")
        if not self.benchmark_before or not self.benchmark_after:
            missing.append("benchmark record")
        if not self.parity:
            missing.append("parity result")
        if not self.rollback_flag:
            missing.append("rollback flag")
        return missing

    @property
    def complete(self) -> bool:
        """True when all four mandatory artifacts are present."""
        return not self.missing_artifacts()

    def expected_active(self) -> Any:
        """The flag value the ACTIVE config must show for this bundle to be honest.

        ``config_after`` when the flip was accepted, the legacy ``config_before``
        when it was auto-reverted.
        """
        snap = self.config_after if self.accepted else self.config_before
        return snap.get(self.flag)


def benchmark_not_worse(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, str]:
    """Return ``(not_worse, reason)`` comparing a before/after benchmark record.

    A benchmark record carries an optional ``suites`` map (suite -> status string) and
    an optional ``tests`` map (``passed``/``failed``/``errors`` counts). The after-record
    is *worse* if any suite verdict regresses (e.g. MET -> FAILED) or the targeted-test
    failure count rises.
    """
    before_suites = before.get("suites", {}) or {}
    after_suites = after.get("suites", {}) or {}
    for suite, b_status in before_suites.items():
        a_status = after_suites.get(suite)
        if a_status is None:
            return False, f"benchmark suite '{suite}' missing after flip"
        if _STATUS_RANK.get(a_status, 1) < _STATUS_RANK.get(b_status, 1):
            return False, f"benchmark suite '{suite}' regressed {b_status} -> {a_status}"

    before_tests = before.get("tests", {}) or {}
    after_tests = after.get("tests", {}) or {}
    b_fail = int(before_tests.get("failed", 0)) + int(before_tests.get("errors", 0))
    a_fail = int(after_tests.get("failed", 0)) + int(after_tests.get("errors", 0))
    if a_fail > b_fail:
        return False, f"targeted tests regressed: {a_fail} failing after vs {b_fail} before"
    return True, "benchmark not worse"


def evaluate_flip(evidence: FlipEvidence) -> FlipEvidence:
    """Decide accept vs auto-revert for *evidence* and stamp ``accepted``/``reverted``.

    Accept iff the bundle is complete AND parity passed AND the after-benchmark is not
    worse than the before-benchmark; otherwise auto-revert with a recorded reason. The
    function mutates and returns *evidence* in place.
    """
    missing = evidence.missing_artifacts()
    if missing:
        evidence.accepted = False
        evidence.reverted = True
        evidence.reason = f"incomplete bundle, missing: {', '.join(missing)}"
        return evidence

    parity_passed = bool(evidence.parity.get("passed"))
    not_worse, bench_reason = benchmark_not_worse(
        evidence.benchmark_before, evidence.benchmark_after
    )
    if parity_passed and not_worse:
        evidence.accepted = True
        evidence.reverted = False
        evidence.reason = "parity passed; benchmark not worse; flip accepted"
    elif not parity_passed:
        evidence.accepted = False
        evidence.reverted = True
        mismatch = evidence.parity.get("mismatch") or "mismatch"
        evidence.reason = f"auto-reverted: parity failed ({mismatch})"
    else:
        evidence.accepted = False
        evidence.reverted = True
        evidence.reason = f"auto-reverted: {bench_reason}"
    return evidence


def flip_bundle_path(root: Path | str, subsystem: str) -> Path:
    """Path to a single subsystem's flip bundle under *root*."""
    return Path(root) / FLIPS_DIR / f"{subsystem}.json"


def write_flip_evidence(root: Path | str, evidence: FlipEvidence) -> Path:
    """Persist *evidence* to ``<root>/.opencontext/flips/<subsystem>.json`` and return it."""
    path = flip_bundle_path(root, evidence.subsystem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(evidence.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def emit_flip_evidence(
    root: Path | str,
    subsystem: str,
    flag: str,
    *,
    config_before: dict[str, Any],
    config_after: dict[str, Any],
    benchmark_before: dict[str, Any],
    benchmark_after: dict[str, Any],
    parity: ParityReport | dict[str, Any],
    rollback_flag: str,
    rollback_path: str,
) -> FlipEvidence:
    """Build, evaluate (accept/auto-revert), and persist one flip evidence bundle."""
    parity_dict = parity.model_dump() if isinstance(parity, ParityReport) else dict(parity)
    evidence = FlipEvidence(
        subsystem=subsystem,
        flag=flag,
        config_before=dict(config_before),
        config_after=dict(config_after),
        benchmark_before=dict(benchmark_before),
        benchmark_after=dict(benchmark_after),
        parity=parity_dict,
        rollback_flag=rollback_flag,
        rollback_path=rollback_path,
        generated_at=datetime.now(UTC).isoformat(),
    )
    evaluate_flip(evidence)
    write_flip_evidence(root, evidence)
    return evidence


def _read_bundle_dir(directory: Path) -> list[FlipEvidence]:
    """Read every valid flip bundle directly under *directory* (sorted by filename).

    A malformed/unreadable bundle is skipped (it is not a valid flip record), never
    fabricated into a pass — honesty (build-rule #1). A missing directory yields ``[]``.
    """
    if not directory.is_dir():
        return []
    bundles: list[FlipEvidence] = []
    for path in sorted(directory.glob("*.json")):
        try:
            bundles.append(FlipEvidence.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return bundles


def read_flip_bundles(root: Path | str, *, subdir: str | None = None) -> list[FlipEvidence]:
    """Read flip bundles for *root*, sorted by subsystem.

    Default (``subdir=None``): the UNION of the committed baseline
    (:data:`FLIP_BASELINE_DIR`, tracked and CI-reproducible) and the runtime directory
    (:data:`FLIPS_DIR`, gitignored). The runtime path WINS on a per-subsystem conflict,
    so a local ``release acceptance`` run can override the committed baseline. A fresh
    checkout with neither directory present yields ``[]`` — never an error.

    Pass an explicit *subdir* (relative to *root*) to read a single directory instead.
    """
    if subdir is not None:
        return _read_bundle_dir(Path(root) / subdir)
    merged: dict[str, FlipEvidence] = {}
    for bundle in _read_bundle_dir(Path(root) / FLIP_BASELINE_DIR):
        merged[bundle.subsystem] = bundle
    for bundle in _read_bundle_dir(Path(root) / FLIPS_DIR):  # runtime overrides baseline
        merged[bundle.subsystem] = bundle
    return sorted(merged.values(), key=lambda bundle: bundle.subsystem)


def active_flag_value(flag: str) -> bool | str | None:
    """The ACTIVE (live config-model default) value for *flag*, or ``None`` if unknown."""
    from opencontext_core.compat.flags import flag_spec

    spec = flag_spec(flag)
    return None if spec is None else spec.default


__all__ = [
    "FLIPS_DIR",
    "FLIP_BASELINE_DIR",
    "FLIP_SCHEMA_VERSION",
    "REQUIRED_ARTIFACTS",
    "FlipEvidence",
    "active_flag_value",
    "benchmark_not_worse",
    "emit_flip_evidence",
    "evaluate_flip",
    "flip_bundle_path",
    "read_flip_bundles",
    "write_flip_evidence",
]
