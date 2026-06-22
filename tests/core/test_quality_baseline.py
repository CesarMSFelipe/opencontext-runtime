"""Behavior tests for the quality baseline store + ratchet diff.

Every test is tmp_path-isolated: the baseline JSON lives under
``tmp_path/.opencontext`` and the real ``~/.opencontext`` / repo ``.opencontext``
are never read or written. These are behavior tests — each asserts an observable
guarantee (round-trip, ratchet-new-only, atomicity, tolerance, key agreement)
and fails if the underlying logic regresses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.quality.baseline import BaselineStore
from opencontext_core.quality.ci_checks import CheckSeverity
from opencontext_core.quality.models import (
    Finding,
    HealthScore,
    QualityMetrics,
    finding_key,
)

# --- fixtures / helpers ----------------------------------------------------


@pytest.fixture
def baseline_path(tmp_path: Path) -> Path:
    """The baseline JSON path under an isolated tmp ``.opencontext`` dir."""
    return tmp_path / ".opencontext" / "quality-baseline.json"


def make_finding(
    rule: str = "max_cc",
    *,
    file: str | None = "src/auth.py",
    line: int | None = 10,
    symbol: str | None = None,
    severity: CheckSeverity = CheckSeverity.WARNING,
    message: str = "complexity 30 > 25",
) -> Finding:
    return Finding(
        rule=rule,
        severity=severity,
        message=message,
        file=file,
        line=line,
        symbol=symbol,
    )


def make_health(score: int = 9000) -> HealthScore:
    metrics = QualityMetrics(max_cc=30, god_files=1)
    return HealthScore(score=score, metrics=metrics, components={"max_cc": 50})


# --- exists / load on a fresh tree -----------------------------------------


def test_exists_false_when_absent(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    assert store.exists() is False
    # Nothing should be created just by constructing / probing the store.
    assert not baseline_path.exists()


def test_load_returns_none_when_absent(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    assert store.load() is None


def test_save_creates_parent_directory(baseline_path: Path) -> None:
    # The .opencontext dir does not exist yet; save must create it.
    assert not baseline_path.parent.exists()
    store = BaselineStore(baseline_path)
    store.save((make_finding(),), QualityMetrics(), make_health())
    assert baseline_path.parent.is_dir()
    assert store.exists() is True


# --- save -> load round-trip ----------------------------------------------


def test_save_then_load_round_trips(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    findings = (
        make_finding("max_cc", file="src/a.py", line=10),
        make_finding("no_god_files", file="src/b.py", line=None, symbol="src/b.py"),
    )
    metrics = QualityMetrics(cycles=2, god_files=1, max_cc=30, node_count=50)
    health = make_health(8800)

    saved = store.save(findings, metrics, health)
    loaded = store.load()

    assert loaded is not None
    assert loaded.score == 8800
    assert loaded.metrics == metrics
    # The reloaded key set equals what save recorded.
    assert loaded.keys == saved.keys
    assert len(loaded.keys) == 2
    # generated_at survives the round-trip and is an ISO-ish non-empty string.
    assert loaded.generated_at == saved.generated_at
    assert loaded.generated_at


def test_saved_json_has_spec_shape(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    f = make_finding("ruff", file="src/x.py", line=5, severity=CheckSeverity.ERROR)
    store.save((f,), QualityMetrics(cycles=1), make_health(9100))

    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    # Top-level keys mandated by the spec (+ score + version).
    assert set(data) >= {"findings", "metrics", "generated_at", "score"}
    assert data["score"] == 9100
    assert data["metrics"]["cycles"] == 1
    assert isinstance(data["findings"], list) and len(data["findings"]) == 1
    row = data["findings"][0]
    assert set(row) >= {"key", "file", "rule", "severity", "symbol_or_line"}
    assert row["rule"] == "ruff"
    assert row["file"] == "src/x.py"
    assert row["severity"] == "error"
    # line-scoped finding -> bucket is the line number.
    assert row["symbol_or_line"] == 5
    # The stored key matches the shared finding_key (line bucket).
    assert row["key"] == finding_key("ruff", "src/x.py", 5)


# --- ratchet diff: only NEW findings ---------------------------------------


def test_diff_returns_only_new_findings(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    pre_existing = make_finding("max_cc", file="src/a.py", line=10)
    store.save((pre_existing,), QualityMetrics(), make_health())
    baseline = store.load()
    assert baseline is not None

    new_finding = make_finding("max_cc", file="src/b.py", line=20)
    current = (pre_existing, new_finding)

    diffed = baseline.diff(current)
    assert diffed == (new_finding,)


def test_diff_empty_when_nothing_new(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    findings = (
        make_finding("max_cc", file="src/a.py", line=10),
        make_finding("ruff", file="src/b.py", line=3),
    )
    store.save(findings, QualityMetrics(), make_health())
    baseline = store.load()
    assert baseline is not None
    # Same findings -> nothing new (the ratchet does not re-flag pre-existing).
    assert baseline.diff(findings) == ()


def test_diff_flags_new_rule_same_location(baseline_path: Path) -> None:
    # A different rule at the SAME file/line is a distinct key -> new finding.
    store = BaselineStore(baseline_path)
    base = make_finding("ruff", file="src/a.py", line=10)
    store.save((base,), QualityMetrics(), make_health())
    baseline = store.load()
    assert baseline is not None

    other_rule = make_finding("max_cc", file="src/a.py", line=10)
    assert baseline.diff((base, other_rule)) == (other_rule,)


def test_diff_symbol_bucket_preferred_over_line(baseline_path: Path) -> None:
    # Symbol-scoped findings bucket on the symbol; moving the LINE but keeping the
    # symbol must NOT be reported as new (the symbol is the stable identity).
    store = BaselineStore(baseline_path)
    base = make_finding("no_god_files", file="src/a.py", line=1, symbol="mod.GodClass")
    store.save((base,), QualityMetrics(), make_health())
    baseline = store.load()
    assert baseline is not None

    moved = make_finding("no_god_files", file="src/a.py", line=999, symbol="mod.GodClass")
    assert baseline.diff((moved,)) == ()

    # But a different symbol in the same file IS new.
    other_symbol = make_finding("no_god_files", file="src/a.py", line=1, symbol="mod.OtherClass")
    assert baseline.diff((other_symbol,)) == (other_symbol,)


def test_key_for_matches_finding_key_symbol_preference(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    # When a symbol is present it must win over the line in the key.
    f_sym = make_finding("no_god_files", file="src/a.py", line=10, symbol="mod.Cls")
    assert store.key_for(f_sym) == finding_key("no_god_files", "src/a.py", "mod.Cls")
    # When no symbol, the line is the bucket.
    f_line = make_finding("max_cc", file="src/a.py", line=10, symbol=None)
    assert store.key_for(f_line) == finding_key("max_cc", "src/a.py", 10)


def test_save_and_diff_keys_agree(baseline_path: Path) -> None:
    # Round-trip guarantee: the key save writes equals the key diff computes, so a
    # saved finding is always suppressed when seen again (no false "new").
    store = BaselineStore(baseline_path)
    findings = (
        make_finding("no_god_files", file="src/a.py", line=10, symbol="mod.Cls"),
        make_finding("max_cc", file="src/b.py", line=7, symbol=None),
    )
    saved = store.save(findings, QualityMetrics(), make_health())
    for f in findings:
        assert store.key_for(f) in saved.keys
    # Reloaded baseline suppresses all of them.
    reloaded = store.load()
    assert reloaded is not None
    assert reloaded.diff(findings) == ()


def test_diff_normalizes_backslash_paths(baseline_path: Path) -> None:
    # finding_key normalizes backslashes -> a Windows-style and POSIX path with the
    # same logical location collide, so the ratchet is cross-platform stable.
    store = BaselineStore(baseline_path)
    posix = make_finding("ruff", file="src/sub/a.py", line=4)
    store.save((posix,), QualityMetrics(), make_health())
    baseline = store.load()
    assert baseline is not None

    windows = make_finding("ruff", file="src\\sub\\a.py", line=4)
    assert baseline.diff((windows,)) == ()


# --- tolerance: corrupt / old / wrong-schema files -------------------------


def test_load_tolerant_of_malformed_json(baseline_path: Path) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("{not: valid json", encoding="utf-8")
    store = BaselineStore(baseline_path)
    # Tolerant: returns None instead of raising on a corrupt file.
    assert store.load() is None


def test_load_tolerant_of_old_schema(baseline_path: Path) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    # A payload missing the modern fields (no 'findings' list).
    baseline_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    store = BaselineStore(baseline_path)
    assert store.load() is None


def test_load_rejects_wrong_version(baseline_path: Path) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(
            {
                "version": 999,
                "findings": [],
                "metrics": {},
                "score": 5000,
                "generated_at": "x",
            }
        ),
        encoding="utf-8",
    )
    store = BaselineStore(baseline_path)
    # Unknown schema version -> treated as "no baseline".
    assert store.load() is None


def test_load_tolerant_of_non_dict_root(baseline_path: Path) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    store = BaselineStore(baseline_path)
    assert store.load() is None


# --- atomicity / determinism ------------------------------------------------


def test_save_is_atomic_no_tmp_left(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    store.save((make_finding(),), QualityMetrics(), make_health())
    # The temp sidecar must be gone after an atomic os.replace.
    tmp = baseline_path.with_name(baseline_path.name + ".tmp")
    assert not tmp.exists()
    assert baseline_path.is_file()


def test_save_overwrites_previous_baseline(baseline_path: Path) -> None:
    store = BaselineStore(baseline_path)
    store.save(
        (make_finding("max_cc", file="src/a.py", line=1),),
        QualityMetrics(),
        make_health(9000),
    )
    store.save(
        (make_finding("ruff", file="src/b.py", line=2),),
        QualityMetrics(cycles=3),
        make_health(8000),
    )
    loaded = store.load()
    assert loaded is not None
    # Second save fully replaces the first.
    assert loaded.score == 8000
    assert loaded.metrics.cycles == 3
    assert len(loaded.keys) == 1
    assert store.key_for(make_finding("ruff", file="src/b.py", line=2)) in loaded.keys
    assert store.key_for(make_finding("max_cc", file="src/a.py", line=1)) not in loaded.keys


def test_save_returns_consistent_baseline(baseline_path: Path) -> None:
    # The Baseline object save returns must match what a subsequent load produces.
    store = BaselineStore(baseline_path)
    findings = (make_finding("max_cc", file="src/a.py", line=10),)
    metrics = QualityMetrics(max_cc=42)
    saved = store.save(findings, metrics, make_health(7777))
    loaded = store.load()
    assert loaded is not None
    assert saved.keys == loaded.keys
    assert saved.score == loaded.score == 7777
    assert saved.metrics == loaded.metrics == metrics
    assert saved.generated_at == loaded.generated_at


def test_empty_findings_baseline(baseline_path: Path) -> None:
    # A clean snapshot (no findings) must still load and flag any later finding.
    store = BaselineStore(baseline_path)
    store.save((), QualityMetrics(node_count=10), make_health(10000))
    baseline = store.load()
    assert baseline is not None
    assert baseline.keys == frozenset()
    assert baseline.score == 10000
    f = make_finding("max_cc", file="src/new.py", line=1)
    assert baseline.diff((f,)) == (f,)


def test_baseline_diff_is_pure(baseline_path: Path) -> None:
    # Diff must be deterministic and not mutate the input tuple.
    store = BaselineStore(baseline_path)
    store.save((make_finding("max_cc", file="src/a.py", line=1),), QualityMetrics(), make_health())
    baseline = store.load()
    assert baseline is not None
    current = (
        make_finding("max_cc", file="src/a.py", line=1),
        make_finding("ruff", file="src/b.py", line=2),
    )
    first = baseline.diff(current)
    second = baseline.diff(current)
    assert first == second
    assert len(current) == 2  # input untouched


# --- isolation guard --------------------------------------------------------


def test_never_touches_real_opencontext(baseline_path: Path, tmp_path: Path) -> None:
    # The path the store operates on is strictly under tmp_path.
    store = BaselineStore(baseline_path)
    store.save((make_finding(),), QualityMetrics(), make_health())
    assert str(baseline_path).startswith(str(tmp_path))
    # Only the tmp baseline file was created under the tmp .opencontext dir.
    created = list((tmp_path / ".opencontext").iterdir())
    assert created == [baseline_path]
