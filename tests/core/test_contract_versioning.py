"""Public-contract versioning enforcement (REL-06, REL-12).

Asserts the book versioning triad (schema_version + compatibility_version +
stability) across the contracts that adopt :class:`VersionedContract`, the
versioned benchmark-methodology stamp, the schema_version literal format, and the
immutability of the AI-eval record.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from opencontext_core.evaluation.models import (
    BenchmarkSuiteReport,
    EvaluationRecord,
    GateStatus,
)
from opencontext_core.models.contract import (
    StabilityLevel,
    VersionedContract,
    compatibility_version_from_schema,
)
from opencontext_core.operating_model.release_gate import AcceptanceVerdict

# The public contracts that adopt the full versioning triad (REL-12).
VERSIONED_CONTRACTS: list[type[VersionedContract]] = [
    BenchmarkSuiteReport,
    EvaluationRecord,
    AcceptanceVerdict,
]

_SCHEMA_RE = re.compile(r"^opencontext\.[a-z0-9_]+\.v\d+$")


def _instance(cls: type[VersionedContract]) -> VersionedContract:
    if cls is BenchmarkSuiteReport:
        return BenchmarkSuiteReport(suite="s", version="1.0.0", status=GateStatus.NOT_MEASURED)
    if cls is EvaluationRecord:
        return EvaluationRecord(target_kind="persona", target_id="x")
    if cls is AcceptanceVerdict:
        return AcceptanceVerdict(ready=False, methodology_version="1.0.0")
    raise AssertionError(cls)


@pytest.mark.parametrize("cls", VERSIONED_CONTRACTS)
def test_contract_carries_the_full_triad(cls: type[VersionedContract]) -> None:
    obj = _instance(cls)
    assert _SCHEMA_RE.match(obj.schema_version), f"{cls.__name__}: bad schema_version"
    assert obj.compatibility_version, f"{cls.__name__}: missing compatibility_version"
    assert isinstance(obj.stability, StabilityLevel), f"{cls.__name__}: missing stability level"


def test_compatibility_version_derives_from_schema() -> None:
    assert compatibility_version_from_schema("opencontext.harness_report.v1") == "v1"
    assert compatibility_version_from_schema("opencontext.context_contract.v2") == "v2"
    # A contract that only set schema_version gets a correct derived compatibility.
    obj = BenchmarkSuiteReport(suite="s", version="1.0.0", status=GateStatus.NOT_MEASURED)
    assert obj.compatibility_version == "v1"


def test_benchmark_methodology_is_versioned() -> None:
    """REL-09: every benchmark report carries a suite name AND a semver version."""
    obj = BenchmarkSuiteReport(
        suite="context-token-efficiency", version="1.0.0", status=GateStatus.MET
    )
    assert obj.suite and re.match(r"^\d+\.\d+\.\d+$", obj.version)


def test_evaluation_record_is_immutable() -> None:
    rec = EvaluationRecord(target_kind="skill", target_id="oc-apply-surgical")
    with pytest.raises(ValidationError):
        rec.success_rate = 1.0  # frozen — audit records cannot be mutated


def test_existing_contract_families_still_carry_schema_version() -> None:
    """Anti-regression for REL-06: the existing families keep their literals."""
    from opencontext_core.harness.models import HarnessReport
    from opencontext_core.models.run_envelope import RunEnvelope

    assert HarnessReport.model_fields["schema_version"].default == "opencontext.harness_report.v1"
    assert _SCHEMA_RE.match(str(RunEnvelope.model_fields["schema_version"].default))
