from __future__ import annotations

from pathlib import Path

from conftest import create_sample_project, write_config
from opencontext_core.runtime import OpenContextRuntime


def test_trace_spans_and_prompt_sections_include_context_pack(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage",
    )

    runtime.index_project(project_root)
    result = runtime.ask("Where is authentication?")
    trace = runtime.load_trace(result.trace_id)

    span_names = {span.name for span in trace.spans}
    assert {
        "workflow.run",
        "project.retrieve",
        "context.rank",
        "context.pack",
        "context.compress",
        "prompt.assemble",
        "llm.generate",
        "trace.persist",
    } <= span_names
    assert trace.spans[1].parent_span_id == trace.spans[0].span_id
    assert "context_pack" in trace.metadata
    assert [section.name for section in trace.prompt_sections][:6] == [
        "system",
        "instructions",
        "tool_schemas",
        "provider_policy_summary",
        "project_manifest",
        "repo_map",
    ]
