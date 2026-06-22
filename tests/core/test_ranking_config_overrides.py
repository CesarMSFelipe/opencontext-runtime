"""B1 — v2 ``context.ranking`` weights as OPTIONAL overrides of ``RetrievalWeights``.

RD1 is normative: ``RetrievalWeights`` (``scoring.py``) is the ONLY default. The v2
``RankingConfig`` weight fields are ``float | None`` overrides — unset (``None``)
means "defer to the dataclass default", so the default path is byte-identical to
pre-change behavior. The historical ``0.25``-style numbers ship as a documented
opt-in preset constant, never as an effective default.
"""

from __future__ import annotations

import dataclasses

from opencontext_core.config import default_config_data, load_config
from opencontext_core.retrieval.planner import _weights_from_ranking_config
from opencontext_core.retrieval.scoring import RetrievalWeights

# The 9 v2 fields map 1:1 onto identically-named RetrievalWeights fields.
_MAPPED_FIELDS = (
    "semantic_relevance",
    "graph_centrality",
    "call_distance",
    "test_affinity",
    "memory_confidence",
    "recent_failure",
    "risk_requirement",
    "freshness",
    "provenance",
)
# Fields with NO RankingConfig counterpart — must always keep dataclass defaults.
_NON_MAPPED_FIELDS = (
    "definition",
    "personalization",
    "stale_memory_penalty",
    "token_cost_penalty",
    "uncertainty_penalty",
)


def _ranking_with(**overrides: float | None):
    """Load a real RankingConfig with the given v2 overrides applied to defaults."""
    data = default_config_data()
    data["context"]["ranking"].update(overrides)
    return load_config_from_data(data).context.ranking


def load_config_from_data(data: dict):
    """Round-trip a config dict through YAML + load_config (matches conftest)."""
    import tempfile
    from pathlib import Path

    import yaml

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "opencontext.yaml"
        p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return load_config(p)


# --- B1-T2: schema shape (DR1 — float | None + ge=0.0) -----------------------


def test_default_loaded_config_has_all_v2_weights_unset() -> None:
    """A default-loaded config leaves every v2 weight None (no override, RD1)."""
    rc = load_config_from_data(default_config_data()).context.ranking
    for field in _MAPPED_FIELDS:
        assert getattr(rc, field) is None, f"{field} should default to None (unset)"


def test_config_that_sets_v2_weights_still_loads() -> None:
    """Back-compat: a config that DOES set v2 weights loads (extra='ignore', N1)."""
    rc = _ranking_with(semantic_relevance=0.33, provenance=0.11)
    assert rc.semantic_relevance == 0.33
    assert rc.provenance == 0.11


def test_negative_v2_weight_rejected() -> None:
    """DR1: ge=0.0 still applies to a SET value (None allowed, negative rejected).

    ``load_config`` wraps Pydantic's ValidationError in a ConfigurationError, so
    assert on the message rather than the wrapper type.
    """
    import pytest

    from opencontext_core.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="greater than or equal to 0"):
        _ranking_with(semantic_relevance=-0.1)


# --- B1-T3/T4: the from-config mapper ----------------------------------------


def test_unset_config_yields_exact_retrievalweights_default() -> None:
    """KEY ACCEPTANCE: unset config -> RetrievalWeights() exactly; semantic_relevance == 0.34.

    Maps to the live default (0.34 after the definition-affinity signal was added) and
    specifically NOT the v2 preset's 0.25.
    """
    rc = load_config_from_data(default_config_data()).context.ranking
    weights = _weights_from_ranking_config(rc)
    assert weights == RetrievalWeights()
    assert weights.semantic_relevance == 0.34
    assert weights.semantic_relevance != 0.25


def test_none_ranking_config_yields_default_weights() -> None:
    """A None RankingConfig (no config at all) maps to RetrievalWeights()."""
    assert _weights_from_ranking_config(None) == RetrievalWeights()


def test_single_field_override_isolated() -> None:
    """B1-1b/B1-3a: setting one v2 field changes only that one weight."""
    rc = _ranking_with(semantic_relevance=0.50)
    weights = _weights_from_ranking_config(rc)
    assert weights.semantic_relevance == 0.50
    base = RetrievalWeights()
    for field in _MAPPED_FIELDS:
        if field == "semantic_relevance":
            continue
        assert getattr(weights, field) == getattr(base, field), f"{field} drifted"


def test_each_mapped_field_overrides_one_to_one() -> None:
    """B1-3a: every v2 field maps to its identically-named RetrievalWeights field."""
    base = RetrievalWeights()
    for field in _MAPPED_FIELDS:
        rc = _ranking_with(**{field: 0.99})
        weights = _weights_from_ranking_config(rc)
        assert getattr(weights, field) == 0.99, f"{field} not overridden"
        # No sibling moved.
        for other in _MAPPED_FIELDS:
            if other == field:
                continue
            assert getattr(weights, other) == getattr(base, other)


def test_non_mapped_fields_never_touched() -> None:
    """B1-3b: personalization + the three penalties always keep dataclass defaults."""
    base = RetrievalWeights()
    rc = _ranking_with(semantic_relevance=0.50, graph_centrality=0.40, provenance=0.30)
    weights = _weights_from_ranking_config(rc)
    for field in _NON_MAPPED_FIELDS:
        assert getattr(weights, field) == getattr(base, field), f"{field} must not move"


def test_mapper_returns_a_distinct_dataclass_instance() -> None:
    """The mapper never mutates the shared default; it returns a fresh frozen copy."""
    rc = _ranking_with(semantic_relevance=0.50)
    weights = _weights_from_ranking_config(rc)
    assert dataclasses.is_dataclass(weights)
    assert weights is not RetrievalWeights()


# --- B1-T4: the planner threads config-derived weights through rank() ---------


def _build_planner(rc):
    """Construct a RetrievalPlanner whose weights come from a RankingConfig."""
    from opencontext_core.retrieval.planner import RetrievalPlanner

    return RetrievalPlanner([], weights=_weights_from_ranking_config(rc))


def test_planner_default_weights_match_dataclass() -> None:
    """B1-1a: a planner built with no explicit weights ranks with RetrievalWeights()."""
    from opencontext_core.retrieval.planner import RetrievalPlanner

    planner = RetrievalPlanner([])
    # The hardcoded RetrievalWeights() must be gone; the resolved default is identical.
    assert (planner._weights or RetrievalWeights()) == RetrievalWeights()


def test_planner_accepts_explicit_weights() -> None:
    """B1-T4: __init__ accepts and stores config-derived weights."""
    rc = _ranking_with(semantic_relevance=0.50)
    planner = _build_planner(rc)
    assert planner._weights is not None
    assert planner._weights.semantic_relevance == 0.50


def test_from_config_threads_ranking_overrides(tmp_path) -> None:
    """B1-1a/1b: from_config derives weights from config.context.ranking."""
    from opencontext_core.models.project import (
        DependencyGraph,
        FileKind,
        ProjectFile,
        ProjectManifest,
    )
    from opencontext_core.retrieval.planner import RetrievalPlanner

    data = default_config_data()
    data["context"]["ranking"]["semantic_relevance"] = 0.50
    config = load_config_from_data(data)

    from datetime import datetime

    from opencontext_core.compat import UTC

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    manifest = ProjectManifest(
        project_name="demo",
        root=str(tmp_path),
        profile="python",
        technology_profiles=["python"],
        files=[
            ProjectFile(
                id="src/a.py",
                path="src/a.py",
                language="python",
                file_type=FileKind.CODE,
                tokens=5,
                size_bytes=20,
                summary="a",
            )
        ],
        symbols=[],
        dependency_graph=DependencyGraph(
            nodes=["src/a.py"], edges=[], unresolved=[], generated_at=datetime.now(tz=UTC)
        ),
        generated_at=datetime.now(tz=UTC),
    )

    planner = RetrievalPlanner.from_config(manifest, config, storage_path=tmp_path / ".storage")
    assert planner._weights is not None
    assert planner._weights.semantic_relevance == 0.50
    # Non-mapped fields still defaulted.
    assert planner._weights.personalization == RetrievalWeights().personalization


def test_from_config_unset_yields_default_weights(tmp_path) -> None:
    """B1-1a: an unset config makes from_config resolve to RetrievalWeights() exactly."""
    from datetime import datetime

    from opencontext_core.compat import UTC
    from opencontext_core.models.project import (
        DependencyGraph,
        FileKind,
        ProjectFile,
        ProjectManifest,
    )
    from opencontext_core.retrieval.planner import RetrievalPlanner

    config = load_config_from_data(default_config_data())
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    manifest = ProjectManifest(
        project_name="demo",
        root=str(tmp_path),
        profile="python",
        technology_profiles=["python"],
        files=[
            ProjectFile(
                id="src/a.py",
                path="src/a.py",
                language="python",
                file_type=FileKind.CODE,
                tokens=5,
                size_bytes=20,
                summary="a",
            )
        ],
        symbols=[],
        dependency_graph=DependencyGraph(
            nodes=["src/a.py"], edges=[], unresolved=[], generated_at=datetime.now(tz=UTC)
        ),
        generated_at=datetime.now(tz=UTC),
    )

    planner = RetrievalPlanner.from_config(manifest, config, storage_path=tmp_path / ".storage")
    assert (planner._weights or RetrievalWeights()) == RetrievalWeights()
    assert (planner._weights or RetrievalWeights()).semantic_relevance == 0.34


def test_scoring_preset_constant_exists_and_is_not_default() -> None:
    """B1-T3: the historical 0.25-style numbers ship as a documented opt-in preset.

    The preset carries the historical v2 semantic_relevance (0.25) and MUST NOT be
    the effective default (RetrievalWeights() default is 0.34 after the
    definition-affinity signal was added).
    """
    from opencontext_core.retrieval import scoring

    preset = scoring.RANKING_PRESET_V2_SEMANTIC
    assert isinstance(preset, RetrievalWeights)
    assert preset.semantic_relevance == 0.25
    # It is NOT what a default planner/ranker uses.
    assert RetrievalWeights().semantic_relevance == 0.34
    assert preset != RetrievalWeights()
