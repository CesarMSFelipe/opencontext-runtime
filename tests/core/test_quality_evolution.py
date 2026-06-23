"""Behavior tests for the per-evaluation quality evolution log.

``EvolutionStore`` appends one ``{timestamp, score, sub_scores}`` row per
evaluation to ``tmp_path/.opencontext/quality-evolution.json`` and returns the
trend (latest / previous / delta / count). Every test is tmp_path-isolated: the
evolution JSON lives under ``tmp_path/.opencontext`` and the real ``~/.opencontext``
/ repo ``.opencontext`` are NEVER read or written.

These are behavior tests — each asserts an observable guarantee (caller-injected
timestamp persisted verbatim, trend math across 0/1/N entries, tolerant + atomic +
deterministic IO, HealthScore bridge) and fails if the logic regresses.

Determinism contract enforced here: the store NEVER calls ``datetime.now`` /
``time`` / ``uuid`` — the caller injects every timestamp — so identical inputs
yield a byte-identical file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from opencontext_core.quality.baseline import BaselineStore
from opencontext_core.quality.evolution import (
    EVOLUTION_FILENAME,
    EvolutionEntry,
    EvolutionStore,
    EvolutionTrend,
    entry_from_health,
)
from opencontext_core.quality.models import HealthScore, QualityMetrics

# --- fixtures / helpers ----------------------------------------------------


@pytest.fixture
def evolution_path(tmp_path: Path) -> Path:
    """The evolution JSON path under an isolated tmp ``.opencontext`` dir.

    Built from the canonical ``EVOLUTION_FILENAME`` so the test exercises the
    exact ``root / EVOLUTION_FILENAME`` layout the runner uses, never the repo.
    """
    return tmp_path / EVOLUTION_FILENAME


def make_health(score: int = 9000, **components: int) -> HealthScore:
    """A HealthScore with a small per-signal components map."""
    if not components:
        components = {"duplication": 60, "nesting": 25}
    metrics = QualityMetrics(max_cc=30, god_files=1)
    return HealthScore(score=score, metrics=metrics, components=dict(components))


# --- construction / path layout --------------------------------------------


def test_filename_is_under_opencontext() -> None:
    # The store records to .opencontext/quality-evolution.json by convention.
    assert EVOLUTION_FILENAME == ".opencontext/quality-evolution.json"


def test_construct_does_not_create_file(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    # Constructing / holding the store must not touch the filesystem.
    assert not evolution_path.exists()
    assert store.path == evolution_path


def test_load_returns_empty_when_absent(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    assert store.load() == ()


def test_trend_on_empty_log(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    trend = store.trend()
    assert isinstance(trend, EvolutionTrend)
    assert trend.latest == 0
    assert trend.previous == 0
    assert trend.delta == 0
    assert trend.count == 0
    assert trend.history == ()
    # trend() is the READ path: it must not create the file.
    assert not evolution_path.exists()


# --- append: caller-injected timestamp persisted verbatim ------------------


def test_append_records_injected_timestamp(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    trend = store.append(
        timestamp="2026-06-22T10:00:00+00:00", score=9100, sub_scores={"duplication": 60}
    )
    assert trend.count == 1
    assert trend.latest == 9100
    # <2 entries: previous == latest, delta == 0.
    assert trend.previous == 9100
    assert trend.delta == 0

    entries = store.load()
    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, EvolutionEntry)
    # The EXACT caller string is persisted (no wall-clock substitution).
    assert entry.timestamp == "2026-06-22T10:00:00+00:00"
    assert entry.score == 9100
    assert entry.sub_scores == {"duplication": 60}


def test_append_creates_parent_directory(evolution_path: Path) -> None:
    # The .opencontext dir does not exist yet; append must create it.
    assert not evolution_path.parent.exists()
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=5000, sub_scores={})
    assert evolution_path.parent.is_dir()
    assert evolution_path.is_file()


def test_store_never_generates_timestamp(evolution_path: Path) -> None:
    # Inject two FIXED strings; the store must persist exactly those, never a
    # generated wall-clock value. This is the determinism / testability contract.
    store = EvolutionStore(evolution_path)
    store.append(timestamp="FIXED-A", score=8000, sub_scores={"nesting": 25})
    store.append(timestamp="FIXED-B", score=8100, sub_scores={"nesting": 0})

    stamps = [e.timestamp for e in store.load()]
    assert stamps == ["FIXED-A", "FIXED-B"]


def _code_tokens(module: object) -> set[str]:
    """Every NAME/ATTRIBUTE token in the module's CODE (docstrings/comments excluded).

    Tokenizing the AST means the guard reacts only to a real ``datetime``/``uuid``/
    ``subprocess`` reference in executable code, not to prose in a docstring that
    merely DESCRIBES the no-wall-clock invariant.
    """
    import ast

    src = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[0])
            if node.asname:
                names.add(node.asname)
    return names


def test_evolution_module_has_no_wallclock_or_uuid_import() -> None:
    # Hard determinism guard: the module CODE must not reference datetime / time /
    # uuid / random / subprocess, so it CANNOT inject a wall-clock or random value
    # (or shell out) behind the caller's back. Zero model + zero subprocess.
    from opencontext_core.quality import evolution as mod

    tokens = _code_tokens(mod)
    for forbidden in ("datetime", "time", "uuid", "random", "subprocess"):
        assert forbidden not in tokens, f"evolution.py code must not reference {forbidden}"
    # os IS allowed (os.replace for the atomic write) but os.system is not.
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "os.system" not in src


# --- trend math across 0 / 1 / N entries -----------------------------------


def test_trend_two_entries_reports_delta(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=9000, sub_scores={})
    trend = store.append(timestamp="t1", score=9200, sub_scores={})
    assert trend.count == 2
    assert trend.latest == 9200
    assert trend.previous == 9000
    assert trend.delta == 200  # latest - previous (improved)


def test_trend_negative_delta_on_regression(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=9200, sub_scores={"duplication": 0})
    trend = store.append(timestamp="t1", score=8900, sub_scores={"duplication": 60})
    # A regression (a new clone) drives the score down -> negative delta.
    assert trend.delta == -300
    assert trend.latest == 8900
    assert trend.previous == 9200


def test_trend_n_entries_uses_last_two(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    for i, score in enumerate((9000, 9100, 9050, 9300)):
        trend = store.append(timestamp=f"t{i}", score=score, sub_scores={})
    # After 4 appends the trend reflects only the final pair (9050 -> 9300).
    assert trend.count == 4
    assert trend.latest == 9300
    assert trend.previous == 9050
    assert trend.delta == 250
    # History preserves chronological (append) order.
    assert [e.score for e in trend.history] == [9000, 9100, 9050, 9300]
    assert [e.timestamp for e in trend.history] == ["t0", "t1", "t2", "t3"]


def test_trend_read_matches_append_return(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=9000, sub_scores={"a": 1})
    returned = store.append(timestamp="t1", score=9400, sub_scores={"a": 2})
    # The trend() read path must agree with what the last append() returned.
    read = store.trend()
    assert read.latest == returned.latest == 9400
    assert read.previous == returned.previous == 9000
    assert read.delta == returned.delta == 400
    assert read.count == returned.count == 2


# --- coercion of inputs -----------------------------------------------------


def test_append_coerces_score_and_subscores_to_int(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    # A JSON-ish float (e.g. 60.0) for a sub-score must round-trip back to an int.
    # json.load yields floats; the typed signature wants ints, so this models the
    # real (loosely-typed) payload the coercion exists to absorb.
    score: Any = 9000.0
    sub_scores: Any = {"dup": 60.0, "nest": 25}
    store.append(timestamp="t0", score=score, sub_scores=sub_scores)
    entry = store.load()[0]
    assert entry.score == 9000
    assert entry.sub_scores == {"dup": 60, "nest": 25}
    assert all(isinstance(v, int) for v in entry.sub_scores.values())
    assert isinstance(entry.score, int)


def test_subscores_persisted_sorted(evolution_path: Path) -> None:
    # sub_scores are written sorted so the file is order-stable regardless of the
    # caller's dict insertion order.
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=9000, sub_scores={"nesting": 25, "duplication": 60})

    data = json.loads(evolution_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1
    row_keys = list(data[0]["sub_scores"].keys())
    assert row_keys == sorted(row_keys) == ["duplication", "nesting"]


# --- tolerance: missing / corrupt / wrong-shape ----------------------------


def test_load_tolerant_of_corrupt_json(evolution_path: Path) -> None:
    evolution_path.parent.mkdir(parents=True, exist_ok=True)
    evolution_path.write_text("{not valid json", encoding="utf-8")
    store = EvolutionStore(evolution_path)
    # Tolerant: corrupt file -> empty, not a raise (mirrors BaselineStore.load).
    assert store.load() == ()
    assert store.trend().count == 0


def test_load_tolerant_of_non_list_payload(evolution_path: Path) -> None:
    evolution_path.parent.mkdir(parents=True, exist_ok=True)
    evolution_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    store = EvolutionStore(evolution_path)
    assert store.load() == ()


def test_load_skips_malformed_rows(evolution_path: Path) -> None:
    # A list containing junk rows keeps the valid ones and drops the invalid ones.
    evolution_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"timestamp": "t0", "score": 9000, "sub_scores": {"d": 1}},  # valid
        {"timestamp": 123, "score": 9000, "sub_scores": {}},  # bad timestamp type
        {"timestamp": "t1", "score": "oops", "sub_scores": {}},  # bad score type
        {"timestamp": "t2", "score": 9100},  # missing sub_scores
        "not-a-dict",  # not even a dict
        {"timestamp": "t3", "score": 9200, "sub_scores": {"d": 2}},  # valid
    ]
    evolution_path.write_text(json.dumps(payload), encoding="utf-8")
    store = EvolutionStore(evolution_path)
    entries = store.load()
    # Only the two well-formed rows survive, order preserved.
    assert [e.timestamp for e in entries] == ["t0", "t3"]
    assert [e.score for e in entries] == [9000, 9200]


def test_append_recovers_from_corrupt_existing_file(evolution_path: Path) -> None:
    # If the existing file is corrupt, append treats it as empty and writes a
    # fresh single-entry list rather than crashing.
    evolution_path.parent.mkdir(parents=True, exist_ok=True)
    evolution_path.write_text("garbage", encoding="utf-8")
    store = EvolutionStore(evolution_path)
    trend = store.append(timestamp="t0", score=9000, sub_scores={})
    assert trend.count == 1
    assert store.load()[0].timestamp == "t0"


# --- atomicity / determinism ------------------------------------------------


def test_write_is_atomic_no_tmp_left(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=9000, sub_scores={})
    # The temp sidecar must be gone after the atomic os.replace.
    tmp = evolution_path.with_name(evolution_path.name + ".tmp")
    assert not tmp.exists()
    assert evolution_path.is_file()


def test_identical_inputs_produce_byte_identical_file(tmp_path: Path) -> None:
    # Determinism: two stores given the SAME injected (timestamp, score, sub_scores)
    # sequence must produce byte-identical files (sort_keys, no wall-clock).
    a = tmp_path / "a" / EVOLUTION_FILENAME
    b = tmp_path / "b" / EVOLUTION_FILENAME
    for path in (a, b):
        store = EvolutionStore(path)
        store.append(timestamp="t0", score=9000, sub_scores={"nesting": 25, "duplication": 60})
        store.append(timestamp="t1", score=9200, sub_scores={"duplication": 0, "nesting": 25})

    assert a.read_bytes() == b.read_bytes()


def test_written_json_is_a_list_of_rows(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=9000, sub_scores={"d": 1})
    store.append(timestamp="t1", score=9100, sub_scores={"d": 2})

    data = json.loads(evolution_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2
    assert all(set(row) >= {"timestamp", "score", "sub_scores"} for row in data)
    assert [row["timestamp"] for row in data] == ["t0", "t1"]


def test_append_grows_history_monotonically(evolution_path: Path) -> None:
    store = EvolutionStore(evolution_path)
    counts = []
    for i in range(5):
        trend = store.append(timestamp=f"t{i}", score=9000 + i, sub_scores={})
        counts.append(trend.count)
    # Each append adds exactly one row; nothing is lost or duplicated.
    assert counts == [1, 2, 3, 4, 5]
    assert len(store.load()) == 5


# --- HealthScore bridge -----------------------------------------------------


def test_entry_from_health_maps_score_and_components() -> None:
    health = make_health(8800, duplication=120, nesting=50)
    row = entry_from_health(health, timestamp="2026-06-22T12:00:00+00:00")
    assert row == {
        "timestamp": "2026-06-22T12:00:00+00:00",
        "score": 8800,
        "sub_scores": {"duplication": 120, "nesting": 50},
    }


def test_entry_from_health_round_trips_through_store(evolution_path: Path) -> None:
    # The bridge dict, when fed to append(), records the health's score+components.
    health = make_health(8700, duplication=60, nesting=25, cycles=0)
    row = entry_from_health(health, timestamp="t0")
    store = EvolutionStore(evolution_path)
    store.append(**row)  # type: ignore[arg-type]
    entry = store.load()[0]
    assert entry.timestamp == "t0"
    assert entry.score == 8700
    assert entry.sub_scores == dict(health.components)


def test_entry_from_health_is_independent_of_health_dict_identity() -> None:
    # The bridge must COPY components, not alias them (mutating the health map
    # later must not corrupt an already-built row).
    components = {"duplication": 60}
    health = HealthScore(score=9000, metrics=QualityMetrics(), components=components)
    row = entry_from_health(health, timestamp="t0")
    components["duplication"] = 999
    assert row["sub_scores"] == {"duplication": 60}


# --- schema invalidation (load-bearing for the Phase-3 metric widening) -----


def test_baseline_schema_version_is_two() -> None:
    # Phase-3 widened QualityMetrics (duplication + max_nesting); the baseline
    # schema MUST bump 1 -> 2 so a pre-Phase-3 baseline is invalidated.
    assert BaselineStore.SCHEMA_VERSION == 2


def test_version_one_baseline_loads_as_none(tmp_path: Path) -> None:
    # A baseline file written under the OLD schema (version 1) must now load as
    # None (stale invalidation -> a fresh snapshot is taken). This is the
    # documented degrade path: old metrics dicts lack the new fields.
    path = tmp_path / ".opencontext" / "quality-baseline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "findings": [],
                "metrics": {"cycles": 0, "god_files": 0},
                "score": 9000,
                "generated_at": "old",
            }
        ),
        encoding="utf-8",
    )
    store = BaselineStore(path)
    assert store.load() is None


# --- isolation guard --------------------------------------------------------


def test_never_touches_real_opencontext(evolution_path: Path, tmp_path: Path) -> None:
    # The path the store operates on is strictly under tmp_path.
    store = EvolutionStore(evolution_path)
    store.append(timestamp="t0", score=9000, sub_scores={})
    assert str(evolution_path).startswith(str(tmp_path))
    # Only the tmp evolution file was created under the tmp .opencontext dir.
    created = list((tmp_path / ".opencontext").iterdir())
    assert created == [evolution_path]
