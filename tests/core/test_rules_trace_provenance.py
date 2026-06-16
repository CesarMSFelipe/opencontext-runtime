"""Rule provenance survives the trace persistence boundary ().

The runtime persists ``prompt.sections`` verbatim into
``RuntimeTrace.prompt_sections`` and reloads the trace via Pydantic JSON. These
tests exercise that exact serialization boundary to prove applied rules are
enumerable from a persisted trace and that overridden rules are not
double-counted as applied.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.assembler import PromptAssembler
from opencontext_core.models.trace import RuntimeTrace
from opencontext_core.rules.loader import RulesConfig, RulesLoader
from opencontext_core.trace.logger import LocalTraceLogger


def _build_trace(prompt_sections: list, *, query: str) -> RuntimeTrace:
    from datetime import datetime

    from opencontext_core.compat import UTC
    from opencontext_core.models.context import TokenBudget

    return RuntimeTrace(
        run_id="rules-trace-test",
        workflow_name="context_pack.local",
        input=query,
        provider="local-only",
        model="none",
        selected_context_items=[],
        discarded_context_items=[],
        token_budget=TokenBudget(
            max_input_tokens=1000,
            reserve_output_tokens=100,
            available_context_tokens=900,
            sections={},
        ),
        token_estimates={},
        compression_strategy="none",
        prompt_sections=prompt_sections,
        final_answer="[LOCAL_ONLY_CONTEXT_PACK]",
        created_at=datetime.now(tz=UTC),
    )


def test_applied_rules_enumerable_from_persisted_trace(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".opencontext" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "a.md").write_text("rule alpha\n", encoding="utf-8")
    (rules_dir / "b.md").write_text("rule beta\n", encoding="utf-8")

    resolved = RulesLoader(RulesConfig()).resolve(project_root=tmp_path)
    prompt = PromptAssembler().assemble("q", [], rules=resolved)

    trace = _build_trace(prompt.sections, query="q")
    logger = LocalTraceLogger(tmp_path / "traces")
    logger.persist(trace)
    loaded = logger.load("rules-trace-test")

    rule_sections = [s for s in loaded.prompt_sections if s.name == "rules"]
    assert len(rule_sections) == 1
    # The count of applied rules enumerable from the trace equals the count
    # injected into the assembled prompt.
    assert len(rule_sections[0].source_ids) == len(resolved.applied)
    assert "rule alpha" in rule_sections[0].content
    assert "rule beta" in rule_sections[0].content


def test_overridden_rule_not_listed_as_applied_in_trace(tmp_path: Path) -> None:
    global_root = tmp_path / "home"
    project_root = tmp_path / "proj"
    global_root.mkdir()
    project_root.mkdir()
    (global_root / ".opencontexthints").write_text(
        "project: G\n\n[conventions]\n- line_length=80\n", encoding="utf-8"
    )
    (project_root / ".opencontexthints").write_text(
        "project: P\n\n[conventions]\n- line_length=120\n", encoding="utf-8"
    )

    resolved = RulesLoader(RulesConfig()).resolve(
        project_root=project_root, global_root=global_root
    )
    prompt = PromptAssembler().assemble("q", [], rules=resolved)
    trace = _build_trace(prompt.sections, query="q")
    logger = LocalTraceLogger(tmp_path / "traces")
    logger.persist(trace)
    loaded = logger.load("rules-trace-test")

    rule_section = next(s for s in loaded.prompt_sections if s.name == "rules")
    # Only the winning project-layer rule is applied / listed.
    assert "line_length=120" in rule_section.content
    assert "line_length=80" not in rule_section.content
    assert len(rule_section.source_ids) == len(resolved.applied) == 1
    # And the override is recorded (observable) in the resolution result.
    assert any(r.content == "line_length=80" for r in resolved.overridden)
