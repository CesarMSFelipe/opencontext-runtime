"""Acceptance: OpenContext's surgical retrieval beats a Gentle-AI-style loop on BOTH
token consumption AND capabilities — the head-to-head that proves the product claim.

The fixture test always runs (CI-reproducible, no network). The real-repo test runs the
full 3-repo panel (slugify/flask/requests) when those clones are present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.evaluation.models import ContextBenchCase
from opencontext_core.evaluation.multi_arm import run_head_to_head
from opencontext_core.evaluation.oc_arm import oc_arm_runner

_FIELDS = (
    "portability",
    "tdd_gate",
    "kg_grounding",
    "impact_consulted",
    "memory_used",
    "spec_artifact",
    "artifact_chain",
    "correctness",
)


def _make_fixture_repo(root: Path) -> None:
    """A small multi-file package: one target function referenced across several modules
    (so a grep-then-read control pays for many files; surgical retrieval pays for one)."""
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text(
        "def process_data(items, strict=False):\n"
        '    """Process and transform a list of items."""\n'
        "    out = []\n"
        "    for item in items:\n"
        "        out.append(item * 2)\n"
        "    return out\n",
        encoding="utf-8",
    )
    for i in range(6):
        (pkg / f"mod{i}.py").write_text(
            "from pkg.core import process_data\n\n"
            f"def handler{i}(data):\n"
            "    # call the shared transform\n"
            "    return process_data(data)\n" + "FILLER = 1\n" * 25,
            encoding="utf-8",
        )


def test_oc_surgical_beats_gentle_and_is_capability_superior(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    _make_fixture_repo(repo)
    case = ContextBenchCase(
        id="fix", query="add input validation to process_data", target_symbol="process_data"
    )

    reports = run_head_to_head([str(repo)], [case], oc_arm_runner=oc_arm_runner)

    assert len(reports) == 1
    rep = reports[0]
    arms = {a.arm: a for a in rep.arms}
    assert {"OC-SURGICAL", "OC-BROAD", "GENTLE-SIM", "REALISTIC-SIN"} <= set(arms)

    # CONSUMPTION: OC's surgical pack is cheaper than Gentle's skill-load + file reads,
    # and cheaper than (or equal to) OC's own broad regression baseline.
    assert arms["OC-SURGICAL"].tokens < arms["GENTLE-SIM"].tokens
    assert arms["OC-SURGICAL"].tokens <= arms["OC-BROAD"].tokens

    # CAPABILITY: OC >= Gentle on every check, strictly greater on the KG-exclusive ones.
    m = rep.matrix
    for fld in _FIELDS:
        assert getattr(m["OC-SURGICAL"], fld) >= getattr(m["GENTLE-SIM"], fld), fld
    assert m["OC-SURGICAL"].kg_grounding and not m["GENTLE-SIM"].kg_grounding
    assert m["OC-SURGICAL"].impact_consulted and not m["GENTLE-SIM"].impact_consulted
    # correctness is MEASURED (target symbol surfaced in the pack), not asserted.
    assert m["OC-SURGICAL"].correctness is True
    # Honesty guard: Gentle IS credited the SDD capabilities it genuinely has.
    assert m["GENTLE-SIM"].memory_used and m["GENTLE-SIM"].spec_artifact


_REAL_REPOS = {
    "/tmp/oc-eval/slugify": ("add a truncate_words parameter to slugify", "slugify"),
    "/tmp/oc-eval/flask": ("add a strict parameter to get_root_path", "get_root_path"),
    "/tmp/oc-eval/requests": ("add a retry_on_status method to Session", "Session"),
}


@pytest.mark.skipif(
    not Path("/tmp/oc-eval/requests").exists(),
    reason="real eval repos (/tmp/oc-eval/*) not present",
)
def test_oc_surgical_beats_both_controls_on_real_repos() -> None:
    for repo, (query, target) in _REAL_REPOS.items():
        if not Path(repo).exists():
            continue
        case = ContextBenchCase(id=Path(repo).name, query=query, target_symbol=target)
        rep = run_head_to_head([repo], [case], oc_arm_runner=oc_arm_runner)[0]
        arms = {a.arm: a for a in rep.arms}
        oc = arms["OC-SURGICAL"].tokens
        gen = arms["GENTLE-SIM"].tokens
        sin = arms["REALISTIC-SIN"].tokens
        assert oc < gen, f"{repo}: OC {oc} !< GENTLE {gen}"
        assert oc < sin, f"{repo}: OC {oc} !< SIN {sin}"
