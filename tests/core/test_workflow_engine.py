from __future__ import annotations

from pathlib import Path

import pytest

from conftest import create_sample_project, write_config
from opencontext_core.config import load_config
from opencontext_core.errors import ConfigurationError
from opencontext_core.indexing.project_indexer import ProjectIndexer
from opencontext_core.llm.mock import MockLLMGateway
from opencontext_core.memory.stores import NullProjectMemoryStore
from opencontext_core.trace.logger import LocalTraceLogger
from opencontext_core.workflow.engine import WorkflowEngine
from opencontext_core.workflow.steps import WorkflowServices


def test_workflow_execution_persists_trace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config = load_config(write_config(tmp_path, project_root))
    manifest = ProjectIndexer(config.project_index, config.project.name).build_manifest(
        project_root
    )
    memory_store = NullProjectMemoryStore()
    memory_store.save_manifest(manifest)
    trace_logger = LocalTraceLogger(tmp_path / "traces")
    services = WorkflowServices(config, memory_store, trace_logger, MockLLMGateway())

    state = WorkflowEngine(config, services).run("code_assistant", "Where is authentication?")

    assert state.trace is not None
    assert state.trace.selected_context_items
    assert trace_logger.load(state.trace.run_id).run_id == state.trace.run_id


def test_sdd_workflow_execution(tmp_path: Path) -> None:
    """Test SDD (Specification-Driven Development) workflow execution."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config = load_config(write_config(tmp_path, project_root))
    manifest = ProjectIndexer(config.project_index, config.project.name).build_manifest(
        project_root
    )
    memory_store = NullProjectMemoryStore()
    memory_store.save_manifest(manifest)
    trace_logger = LocalTraceLogger(tmp_path / "traces")
    services = WorkflowServices(config, memory_store, trace_logger, MockLLMGateway())

    # The sdd workflow should execute without errors
    state = WorkflowEngine(config, services).run("sdd", "Where is authentication?")

    assert state.trace is not None
    assert state.workflow_name == "sdd"
    # Should have executed the sdd steps
    step_names = [step.name for step in state.step_results]
    # At minimum project.load_manifest should be executed
    assert any("project." in step or "context." in step for step in step_names)
    assert trace_logger.load(state.trace.run_id).run_id == state.trace.run_id


def test_sdd_apply_workflow_execution(tmp_path: Path) -> None:
    """Test SDD apply workflow execution with all steps."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config = load_config(write_config(tmp_path, project_root))
    manifest = ProjectIndexer(config.project_index, config.project.name).build_manifest(
        project_root
    )
    memory_store = NullProjectMemoryStore()
    memory_store.save_manifest(manifest)
    trace_logger = LocalTraceLogger(tmp_path / "traces")
    services = WorkflowServices(config, memory_store, trace_logger, MockLLMGateway())

    # The sdd_apply workflow includes all SDD steps
    state = WorkflowEngine(config, services).run("sdd_apply", "Implement feature X")

    assert state.trace is not None
    assert state.workflow_name == "sdd_apply"
    step_names = [step.name for step in state.step_results]
    # Should have executed multiple SDD steps
    assert any("context." in step for step in step_names)
    assert trace_logger.load(state.trace.run_id).run_id == state.trace.run_id


def test_unknown_workflow_step_raises_configuration_error(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config = load_config(write_config(tmp_path, project_root))
    config.workflows["broken"] = config.workflows["code_assistant"].model_copy(
        update={"steps": ["unknown.step"]}
    )
    services = WorkflowServices(
        config,
        NullProjectMemoryStore(),
        LocalTraceLogger(tmp_path / "traces"),
        MockLLMGateway(),
    )

    with pytest.raises(ConfigurationError, match="Unknown workflow step"):
        WorkflowEngine(config, services).run("broken", "test")


def test_sdd_context_explore_step(tmp_path: Path) -> None:
    """Test context.explore step produces candidates."""
    from opencontext_core.memory.stores import NullProjectMemoryStore
    from opencontext_core.models.workflow import WorkflowRunState
    from opencontext_core.trace.logger import LocalTraceLogger
    from opencontext_core.workflow.steps import WorkflowServices, context_explore

    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config = load_config(write_config(tmp_path, project_root))
    manifest = ProjectIndexer(config.project_index, config.project.name).build_manifest(
        project_root
    )
    memory_store = NullProjectMemoryStore()
    memory_store.save_manifest(manifest)
    trace_logger = LocalTraceLogger(tmp_path / "traces")
    services = WorkflowServices(config, memory_store, trace_logger, MockLLMGateway())
    state = WorkflowRunState(run_id="test", workflow_name="test", user_request="test auth")
    state.manifest = manifest

    result = context_explore(state, services)
    assert "explored" in result
    # Explore stores results in metadata, not as direct attribute
    assert "explored_context" in state.metadata
    assert len(state.metadata["explored_context"]) > 0


def test_sdd_context_propose_step(tmp_path: Path) -> None:
    """Test context.propose step produces a context pack proposal."""
    from opencontext_core.memory.stores import NullProjectMemoryStore
    from opencontext_core.models.context import ContextItem
    from opencontext_core.models.workflow import WorkflowRunState
    from opencontext_core.trace.logger import LocalTraceLogger
    from opencontext_core.workflow.steps import WorkflowServices, context_propose

    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config = load_config(write_config(tmp_path, project_root))
    manifest = ProjectIndexer(config.project_index, config.project.name).build_manifest(
        project_root
    )
    memory_store = NullProjectMemoryStore()
    memory_store.save_manifest(manifest)
    trace_logger = LocalTraceLogger(tmp_path / "traces")
    services = WorkflowServices(config, memory_store, trace_logger, MockLLMGateway())
    state = WorkflowRunState(run_id="test", workflow_name="test", user_request="test auth")
    state.manifest = manifest
    # Pre-populate explored context in metadata
    state.metadata["explored_context"] = [
        ContextItem(
            id=f"test-{i}",
            content=f"test content {i}",
            source=f"test{i}.py",
            source_type="module",
            priority=0,
            tokens=100,
            score=0.9 - i * 0.1,
            classification="internal",
            trusted=True,
            metadata={},
            redacted=False,
        ).model_dump(mode="json")
        for i in range(5)
    ]

    result = context_propose(state, services)
    assert "proposed" in result
    assert "proposed_context" in state.metadata
    assert state.metadata["proposed_context"]["included"]
