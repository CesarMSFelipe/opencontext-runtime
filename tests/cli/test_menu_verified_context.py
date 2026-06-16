from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from opencontext_cli.commands.verified_context_view import (
    aicx_reduction_pct,
    gather_kg_status,
    render_kg_header,
    render_verified_context,
    renderable_to_text,
    trust_badge,
)
from opencontext_core.config import default_config_data
from opencontext_core.retrieval.contracts import VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime


def _write_config(tmp_path: Path, project_root: Path) -> Path:
    data = default_config_data()
    data["project"]["name"] = "menu-test-project"
    data["project_index"]["root"] = str(project_root)
    data["retrieval"]["top_k"] = 10
    data["retrieval"]["rerank_top_k"] = 5
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _create_sample_project(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "class AuthService:",
                "    def login(self, username: str) -> bool:",
                "        return bool(username)",
                "",
                "def audit_login(username: str) -> str:",
                "    return username",
            ]
        ),
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Sample\nAuthentication lives in src/auth.py\n",
        encoding="utf-8",
    )


def _indexed_runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=str(_write_config(tmp_path, project_root)),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project_root)
    return runtime, project_root


def test_gather_kg_status_returns_index_stats(tmp_path: Path) -> None:
    _indexed_runtime(tmp_path)

    # The helper looks under <root>/.storage/opencontext; the runtime above used
    # exactly that layout, so the manifest is discoverable.
    status = gather_kg_status(tmp_path)

    assert status.indexed is True
    assert status.files >= 1
    assert status.symbols >= 1
    assert status.generated_at is not None


def test_gather_kg_status_unindexed_is_safe(tmp_path: Path) -> None:
    status = gather_kg_status(tmp_path / "nowhere")
    assert status.indexed is False
    assert status.detail


def test_render_kg_header_shows_counts(tmp_path: Path) -> None:
    status = SimpleNamespace(
        indexed=True,
        files=12,
        symbols=34,
        nodes=56,
        edges=78,
        profiles=["python"],
        age_label="just now",
    )
    text = renderable_to_text(render_kg_header(status))  # type: ignore[arg-type]
    assert "12 files" in text
    assert "34 symbols" in text
    assert "56 graph nodes" in text
    assert "indexed" in text


def test_render_kg_header_unindexed() -> None:
    status = SimpleNamespace(indexed=False, detail="not indexed — run 'opencontext index .'")
    text = renderable_to_text(render_kg_header(status))  # type: ignore[arg-type]
    assert "Not indexed" in text


def _passing_result() -> SimpleNamespace:
    return SimpleNamespace(
        trace_id="trace-xyz",
        evidence=[SimpleNamespace(source="src/auth.py", tokens=400)],
        memory=[],
        gates=[
            SimpleNamespace(name="provenance", passed=True, reason="ok", risks=[]),
            SimpleNamespace(name="freshness", passed=True, reason="ok", risks=[]),
        ],
        risk_level="normal",
        trust_decision=SimpleNamespace(status="sufficient", reason="ok"),
        token_usage={"final_context_pack": 120, "baseline_project": 2000},
        omitted_sources=["vector_disabled"],
        aicx={"v": "AICX1", "r": "req", "d": {}, "i": [["EVID", "auth"]], "chk": "abc123"},
    )


def test_render_verified_context_card_is_scannable() -> None:
    text = renderable_to_text(render_verified_context(_passing_result(), query="fix auth"))

    # Trust badge
    assert "TRUSTED" in text
    # Gate names with pass markers
    assert "provenance" in text
    assert "freshness" in text
    # Risk level
    assert "normal" in text
    # Token usage / reduction (savings)
    assert "120 tokens" in text
    assert "smaller" in text
    # AICX transport reduction line present
    assert "AICX" in text
    # Included sources
    assert "src/auth.py" in text
    # Trace id surfaced
    assert "trace-xyz" in text


def test_render_verified_context_failed_gate_marks_partial_or_unverified() -> None:
    result = SimpleNamespace(
        trace_id="trace-fail",
        evidence=[],
        memory=[],
        gates=[SimpleNamespace(name="provenance", passed=False, reason="no evidence", risks=["x"])],
        risk_level="high",
        trust_decision=SimpleNamespace(status="insufficient", reason="gate failed"),
        token_usage={"final_context_pack": 0},
        omitted_sources=["manifest_unavailable"],
        aicx=None,
    )
    text = renderable_to_text(render_verified_context(result, query="secrets"))
    assert "UNVERIFIED" in text
    assert "provenance" in text
    assert "no evidence" in text
    assert "high" in text


def test_trust_badge_levels() -> None:
    passing = _passing_result()
    assert "TRUSTED" in trust_badge(passing).plain

    partial = _passing_result()
    partial.gates = [SimpleNamespace(name="freshness", passed=False, reason="stale", risks=[])]
    partial.risk_level = "normal"
    assert "PARTIAL" in trust_badge(partial).plain


def test_aicx_reduction_pct_from_result_fields() -> None:
    result = _passing_result()
    reduction = aicx_reduction_pct(result)
    assert reduction is not None
    assert reduction > 0

    # No evidence tokens -> no reduction to report.
    empty = SimpleNamespace(evidence=[], aicx={"i": [], "d": {}, "v": "AICX1", "chk": "z"})
    assert aicx_reduction_pct(empty) is None


def test_render_verified_context_with_real_runtime(tmp_path: Path) -> None:
    runtime, project_root = _indexed_runtime(tmp_path)
    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Where is authentication implemented?",
            root=project_root,
            max_tokens=1200,
        )
    )
    text = renderable_to_text(render_verified_context(result, query="auth"))

    # Every gate the runtime produced is named in the card.
    for gate in result.gates:
        assert gate.name in text
    # Risk level rendered.
    assert str(result.risk_level.value) in text
    # Token usage surfaced.
    assert "tokens in context pack" in text
