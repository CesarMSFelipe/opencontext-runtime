"""Built-in workflow steps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from opencontext_core.compat import UTC
from opencontext_core.config import OpenContextConfig
from opencontext_core.context.assembler import PromptAssembler
from opencontext_core.context.budgeting import TokenBudgetManager
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.packing import ContextPackBuilder
from opencontext_core.context.ranking import ContextRanker
from opencontext_core.errors import WorkflowExecutionError
from opencontext_core.indexing.repo_map import RepoMapEngine
from opencontext_core.llm.gateway import LLMGateway
from opencontext_core.memory.stores import ProjectMemoryStore
from opencontext_core.models.context import (
    AssembledPrompt,
    ContextItem,
    ContextPriority,
    TokenBudget,
)
from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.models.project import ProjectManifest
from opencontext_core.models.trace import RuntimeTrace, TraceEvent, TraceSpan
from opencontext_core.models.workflow import WorkflowRunState
from opencontext_core.retrieval.retriever import ProjectRetriever
from opencontext_core.safety.classification import enforce_classification_invariants
from opencontext_core.safety.firewall import ContextFirewall
from opencontext_core.safety.redaction import SinkGuard
from opencontext_core.safety.trace_sanitizer import TraceSanitizer
from opencontext_core.trace.logger import LocalTraceLogger


@dataclass(frozen=True)
class WorkflowServices:
    """Services available to workflow steps."""

    config: OpenContextConfig
    memory_store: ProjectMemoryStore
    trace_logger: LocalTraceLogger
    llm_gateway: LLMGateway
    embedding_worker: Any | None = None  # Optional[AsyncEmbeddingWorker]
    tunnel_store: Any | None = None  # Optional[GraphTunnelStore] - for cross-project tunnels


def project_load_manifest(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Load the persisted project manifest."""

    state.manifest = services.memory_store.load_manifest()
    return f"loaded manifest with {len(state.manifest.files)} files"


def project_retrieve(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Retrieve candidate context from the manifest, optionally with cross-project links."""

    manifest = _require_manifest(state)
    top_k = services.config.retrieval.top_k

    # Check if cross-project retrieval is enabled and tunnel store available
    if services.config.retrieval.cross_project.enabled and services.tunnel_store is not None:
        from opencontext_core.retrieval.cross_project import CrossProjectRetriever

        state.retrieved_context = CrossProjectRetriever(
            manifest=manifest,
            tunnel_store=services.tunnel_store,
            auto_discover=services.config.retrieval.cross_project.auto_discover,
            max_tokens_per_project=services.config.retrieval.cross_project.max_tokens_per_project,
        ).retrieve(state.user_request, top_k=top_k)
    else:
        state.retrieved_context = ProjectRetriever(manifest).retrieve(
            state.user_request, top_k=top_k
        )

    return f"retrieved {len(state.retrieved_context)} candidates"


def context_rank(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Rank retrieved context and enforce the retrieved-context token budget."""

    manager = TokenBudgetManager(services.config.context)
    state.token_budget = manager.calculate()
    ranker = ContextRanker(services.config.context.ranking.weights)
    state.ranked_context = ranker.rank(state.retrieved_context)
    rerank_limit = services.config.retrieval.rerank_top_k
    reranked = state.ranked_context[:rerank_limit]
    overflow = [
        _discard(item, "rerank_top_k_exceeded") for item in state.ranked_context[rerank_limit:]
    ]
    selected, budget_discards = manager.select_within_budget(reranked, "retrieved_context")
    state.selected_context = selected
    state.discarded_context = [*overflow, *budget_discards]
    state.metadata["token_estimates_before_optimization"] = sum(
        item.tokens for item in state.retrieved_context
    )
    return f"ranked {len(state.ranked_context)} candidates and selected {len(selected)}"


def context_pack(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Pack ranked context under the retrieved-context budget."""

    budget = _require_budget(state)
    ranked = state.ranked_context or state.retrieved_context
    rerank_limit = services.config.retrieval.rerank_top_k
    candidates = ranked[:rerank_limit]
    overflow = [_discard(item, "rerank_top_k_exceeded") for item in ranked[rerank_limit:]]
    required_priorities = {
        _priority_from_name(name) for name in services.config.context_packing.preserve_priorities
    }
    available_tokens = min(
        budget.available_context_tokens,
        budget.sections.get("retrieved_context", budget.available_context_tokens),
    )
    pack_result = ContextPackBuilder().pack(
        candidates,
        available_tokens=available_tokens,
        required_priorities=required_priorities,
    )
    state.context_pack = pack_result
    state.selected_context = pack_result.included
    state.discarded_context = [*pack_result.omitted, *overflow]
    state.metadata["context_pack"] = pack_result.model_dump(mode="json")
    state.metadata["token_estimates_after_packing"] = pack_result.used_tokens
    return (
        f"packed {len(pack_result.included)} items using {pack_result.used_tokens} "
        f"of {available_tokens} tokens"
    )


def context_compress(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Compress selected context and keep it within budget."""

    budget = _require_budget(state)
    section_budget = min(
        budget.available_context_tokens,
        budget.sections.get("retrieved_context", budget.available_context_tokens),
    )
    engine = CompressionEngine(services.config.context.compression)
    compressed_items, results = engine.compress_items(state.selected_context, section_budget)
    state.selected_context = compressed_items
    state.metadata["compression_results"] = [result.model_dump(mode="json") for result in results]
    state.metadata["token_estimates_after_optimization"] = sum(
        item.tokens for item in state.selected_context
    )
    return f"compressed {len(results)} items to {len(compressed_items)} selected items"


def context_explore(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Explore phase: retrieve and rank candidates without packing (SDD style)."""
    manifest = _require_manifest(state)
    retriever = ProjectRetriever(manifest)
    candidates = retriever.retrieve(
        state.user_request,
        top_k=services.config.retrieval.top_k,
    )
    state.metadata["explored_context"] = [c.model_dump(mode="json") for c in candidates]
    return f"explored {len(candidates)} candidate sources"


def context_propose(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Propose phase: rank and prepare context pack proposal without execution (SDD style)."""
    if state.token_budget is not None:
        budget = state.token_budget
    else:
        manager = TokenBudgetManager(services.config.context)
        budget = manager.calculate()
        state.token_budget = budget

    if state.ranked_context:
        ranked = state.ranked_context
    elif state.retrieved_context:
        ranked = state.retrieved_context
    elif "explored_context" in state.metadata:
        from opencontext_core.models.context import ContextItem

        ranked = [ContextItem.model_validate(c) for c in state.metadata["explored_context"]]
        ranker = ContextRanker(services.config.context.ranking.weights)
        ranked = ranker.rank(ranked)
    else:
        ranked = []
    rerank_limit = services.config.retrieval.rerank_top_k
    candidates = ranked[:rerank_limit]
    required_priorities = {
        _priority_from_name(name) for name in services.config.context_packing.preserve_priorities
    }
    available_tokens = min(
        budget.available_context_tokens,
        budget.sections.get("retrieved_context", budget.available_context_tokens),
    )
    pack_result = ContextPackBuilder().pack(
        candidates,
        available_tokens=available_tokens,
        required_priorities=required_priorities,
    )
    state.metadata["proposed_context"] = pack_result.model_dump(mode="json")
    state.metadata["proposal"] = pack_result.model_dump(mode="json")
    return (
        f"proposed {len(pack_result.included)} items using {pack_result.used_tokens} "
        f"of {available_tokens} tokens (proposal only)"
    )


def _require_proposal(state: WorkflowRunState, message: str) -> Any:
    """Return the validated proposal context pack, or raise if no propose phase ran.

    ``context_propose`` writes both ``proposed_context`` (read by trace persistence)
    and ``proposal``; either is accepted here so every downstream phase shares one
    guard+validate instead of repeating it.
    """
    from opencontext_core.models.context import ContextPackResult

    raw = state.metadata.get("proposed_context") or state.metadata.get("proposal")
    if raw is None:
        raise WorkflowExecutionError(message)
    return ContextPackResult.model_validate(raw)


def context_apply(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Apply phase: execute proposed changes with safety checks (SDD style)."""
    proposal = _require_proposal(state, "No proposal to apply. Run propose phase first.")
    return (
        f"applied proposal: {len(proposal.included)} context items ready for "
        f"implementation (safe execution scaffold)"
    )


def context_test(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Test phase: validate proposed changes (SDD style)."""
    from opencontext_core.safety.classification import enforce_classification_invariants

    proposal = _require_proposal(state, "No proposal to test.")

    enforce_classification_invariants(
        proposal.included, proposal.omitted, state.prompt if hasattr(state, "prompt") else None
    )

    firewall = ContextFirewall(services.config)
    gate_result = firewall.check_context_export(
        [*proposal.included, *proposal.omitted],
        sink="test_validation",
    )
    if not gate_result.allowed:
        raise WorkflowExecutionError(f"Test validation failed: {gate_result.reason}")

    return f"test validation passed: {len(proposal.included)} items safe to proceed"


def context_verify(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Verify phase: comprehensive verification (SDD style)."""
    _require_proposal(state, "No proposal to verify.")

    from pathlib import Path

    from opencontext_core.dx.security_reports import scan_project

    scan = scan_project(Path("."))
    state.metadata["verification_scan"] = scan.model_dump(mode="json")

    severity = "high" if scan.findings else "none"
    return f"verification complete: {severity} severity, {len(scan.findings)} findings"


def context_review(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Review phase: final review and approval (SDD style)."""
    proposal = _require_proposal(state, "No proposal to review.")

    high_risk_items = [
        item for item in proposal.included if item.classification.value in ("secret", "regulated")
    ]

    if high_risk_items:
        state.metadata["review_flags"] = {
            "high_risk_items": len(high_risk_items),
            "requires_approval": True,
        }
        return f"review requires approval: {len(high_risk_items)} high-risk items detected"

    state.metadata["review_approved"] = True
    return f"review approved: {len(proposal.included)} items ready for deployment"


def context_archive(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Archive phase: persist and clean up (SDD style)."""
    proposal = _require_proposal(state, "No proposal to archive.")

    return f"archived proposal: {len(proposal.included)} items archived"


def context_up_code(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Up-code phase: update code with proposal (SDD style)."""
    proposal = _require_proposal(state, "No proposal to up-code.")

    state.metadata["upcode_suggestions"] = {
        "items_count": len(proposal.included),
        "provider": services.config.models.default.provider,
        "model": services.config.models.default.model,
    }
    return f"up-code generated: {len(proposal.included)} items ready for code update"


def trace_sdd_persist(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Persist a trace for SDD workflows (without LLM calls)."""
    trace_id = uuid4().hex
    root_span_id = uuid4().hex[:16]
    now = datetime.now(tz=UTC)
    budget = (
        state.token_budget
        if state.token_budget
        else TokenBudgetManager(services.config.context).calculate()
    )

    from opencontext_core.models.context import ContextPackResult

    proposed_context_items = []
    if "proposed_context" in state.metadata:
        pc = ContextPackResult.model_validate(state.metadata["proposed_context"])
        proposed_context_items = pc.included
    elif state.metadata.get("proposal"):
        pc = ContextPackResult.model_validate(state.metadata["proposal"])
        proposed_context_items = pc.included

    verification_scan = state.metadata.get("verification_scan", {})

    trace = RuntimeTrace(
        run_id=state.run_id,
        trace_id=trace_id,
        span_id=root_span_id,
        parent_span_id=None,
        name="workflow.run",
        start_time=state.step_results[0].start_time if state.step_results else now,
        end_time=now,
        attributes={
            "workflow.name": state.workflow_name,
            "context.selected_count": len(proposed_context_items),
            "verification_findings": len(verification_scan.get("findings", [])),
        },
        events=[
            TraceEvent(
                name="context.pack.decisions",
                timestamp=now,
                attributes={
                    "omissions": state.metadata.get("proposed_context", {}).get("omissions", [])
                    if isinstance(state.metadata.get("proposed_context"), dict)
                    else [],
                },
            )
            if state.metadata.get("proposed_context")
            else TraceEvent(
                name="workflow.start",
                timestamp=now,
                attributes={},
            )
        ],
        spans=_build_spans(state, trace_id, root_span_id),
        workflow_name=state.workflow_name,
        input=state.user_request,
        provider="local-only",
        model="none",
        selected_context_items=proposed_context_items,
        discarded_context_items=[],
        token_budget=budget,
        token_estimates={
            "selected_after_optimization": sum(i.tokens for i in proposed_context_items),
            "prompt": 0,
            "llm_input": 0,
            "llm_output": 0,
        },
        compression_strategy=services.config.context.compression.strategy.value,
        prompt_sections=[],
        final_answer="[SDD workflow completed]",
        timings_ms={
            step.name: step.duration_ms
            for step in state.step_results
            if step.name != "trace.persist"
        },
        errors=[],
        created_at=now,
        metadata={
            "sdd_workflow": True,
            "verification_scan": verification_scan,
            "proposal": state.metadata.get("proposed_context")
            or state.metadata.get("proposal", {}),
            "step_results": [step.model_dump() for step in state.step_results],
        },
    )
    sanitized_trace = TraceSanitizer().sanitize(trace, services.config.security.mode)
    ContextFirewall(services.config).check_trace_persistence(sanitized_trace).raise_if_blocked()
    state.trace = sanitized_trace
    services.trace_logger.persist(sanitized_trace)
    return f"persisted SDD trace {trace.run_id}"


def prompt_assemble(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Assemble the final prompt."""

    assembler = PromptAssembler()
    manifest = state.manifest
    project_manifest_summary = _project_manifest_summary(manifest) if manifest else ""
    repo_map_text = ""
    if manifest is not None and services.config.repo_map.enabled:
        repo_map = RepoMapEngine().build(manifest, state.user_request)
        repo_map_text = RepoMapEngine().render(repo_map, services.config.repo_map.max_tokens)

    extra_instructions = ""
    or_cfg = services.config.context.compression.output_reducer
    if or_cfg.enabled:
        from opencontext_core.compression.output_reducer import OutputReducer

        extra_instructions = OutputReducer(
            verbosity_instruction=or_cfg.verbosity_instruction,
            effort_routing=or_cfg.effort_routing,
            holdout_fraction=or_cfg.holdout_fraction,
        ).build_verbosity_instruction()

    state.prompt = assembler.assemble(
        state.user_request,
        state.selected_context,
        provider_policy_summary=_provider_policy_summary(services.config),
        project_manifest=project_manifest_summary,
        repo_map=repo_map_text,
        workflow_contract=(
            "Use stable prefix sections first, then retrieved context, then the current input. "
            "Do not use omitted context."
        ),
        instructions=extra_instructions,
    )
    return f"assembled prompt with {state.prompt.total_tokens} estimated tokens"


def llm_generate(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Generate a response through the configured LLM gateway."""

    prompt = _require_prompt(state)
    model_config = services.config.models.default
    sanitized_items = _sanitize_context_for_sink(state.selected_context)
    state.selected_context = sanitized_items
    request = LLMRequest(
        prompt=prompt.content,
        provider=model_config.provider,
        model=model_config.model,
        max_output_tokens=services.config.context.reserve_output_tokens,
        context_items=sanitized_items,
        metadata={"workflow_name": state.workflow_name, "run_id": state.run_id},
    )
    decision = ContextFirewall(services.config).check_provider_call(
        request.provider,
        sanitized_items,
        provider_metadata={
            "private_endpoint": model_config.private_endpoint,
            "training_opt_in": model_config.training_opt_in,
            "zero_data_retention": model_config.zero_data_retention,
        },
    )
    if not decision.allowed:
        classifications = sorted({item.classification.value for item in sanitized_items})
        raise WorkflowExecutionError(
            "\n".join(
                [
                    "Blocked by provider policy.",
                    "",
                    "Reason:",
                    f"- Decision: {decision.reason}",
                    f"- Provider: {request.provider}",
                    f"- Context classifications: {', '.join(classifications) or 'none'}",
                    f"- Security mode: {services.config.security.mode.value}",
                    "",
                    "Options:",
                    "1. Use the mock/local provider.",
                    "2. Redact or omit high-risk context.",
                    "3. Use a lower-risk mode such as plan with repo map only.",
                    "4. Update provider policy explicitly.",
                ]
            )
        )
    state.metadata["provider_policy_decision"] = decision.model_dump(mode="json")
    state.llm_response = services.llm_gateway.generate(request)
    return "generated deterministic LLM response"


def trace_persist(state: WorkflowRunState, services: WorkflowServices) -> str:
    """Build and persist the runtime trace."""

    prompt = _require_prompt(state)
    response = _require_response(state)
    budget = _require_budget(state)
    enforce_classification_invariants(state.selected_context, state.discarded_context, prompt)
    trace_id = uuid4().hex
    root_span_id = uuid4().hex[:16]
    trace = RuntimeTrace(
        run_id=state.run_id,
        trace_id=trace_id,
        span_id=root_span_id,
        parent_span_id=None,
        name="workflow.run",
        start_time=state.step_results[0].start_time if state.step_results else datetime.now(tz=UTC),
        end_time=datetime.now(tz=UTC),
        attributes={
            "workflow.name": state.workflow_name,
            "llm.provider": response.provider,
            "llm.model": response.model,
            "context.selected_count": len(state.selected_context),
            "context.discarded_count": len(state.discarded_context),
        },
        events=[
            TraceEvent(
                name="context.pack.decisions",
                timestamp=datetime.now(tz=UTC),
                attributes={
                    "omissions": state.metadata.get("context_pack", {}).get("omissions", [])
                    if isinstance(state.metadata.get("context_pack"), dict)
                    else [],
                },
            )
        ],
        spans=_build_spans(state, trace_id, root_span_id),
        workflow_name=state.workflow_name,
        input=state.user_request,
        provider=response.provider,
        model=response.model,
        selected_context_items=state.selected_context,
        discarded_context_items=state.discarded_context,
        token_budget=budget,
        token_estimates={
            "retrieved_before_optimization": int(
                state.metadata.get("token_estimates_before_optimization", 0)
            ),
            "selected_after_optimization": int(
                state.metadata.get("token_estimates_after_optimization", 0)
            ),
            "prompt": prompt.total_tokens,
            "llm_input": response.input_tokens,
            "llm_output": response.output_tokens,
        },
        compression_strategy=services.config.context.compression.strategy.value,
        prompt_sections=prompt.sections,
        final_answer=response.content,
        timings_ms={
            step.name: step.duration_ms
            for step in state.step_results
            if step.name != "trace.persist"
        },
        errors=[],
        created_at=datetime.now(tz=UTC),
        metadata={
            "compression_results": state.metadata.get("compression_results", []),
            "context_pack": state.metadata.get("context_pack", {}),
            "step_results": [step.model_dump() for step in state.step_results],
        },
    )
    sanitized_trace = TraceSanitizer().sanitize(trace, services.config.security.mode)
    ContextFirewall(services.config).check_trace_persistence(sanitized_trace).raise_if_blocked()
    state.trace = sanitized_trace
    services.trace_logger.persist(sanitized_trace)
    return f"persisted trace {trace.run_id}"


def _require_manifest(state: WorkflowRunState) -> ProjectManifest:
    if state.manifest is None:
        raise WorkflowExecutionError("Workflow state has no loaded project manifest.")
    return state.manifest


def _require_budget(state: WorkflowRunState) -> TokenBudget:
    if state.token_budget is None:
        raise WorkflowExecutionError("Workflow state has no calculated token budget.")
    return state.token_budget


def _require_prompt(state: WorkflowRunState) -> AssembledPrompt:
    if state.prompt is None:
        raise WorkflowExecutionError("Workflow state has no assembled prompt.")
    return state.prompt


def _require_response(state: WorkflowRunState) -> LLMResponse:
    if state.llm_response is None:
        raise WorkflowExecutionError("Workflow state has no LLM response.")
    return state.llm_response


def _discard(item: ContextItem, reason: str) -> ContextItem:
    metadata = dict(item.metadata)
    metadata["discard_reason"] = reason
    return item.model_copy(update={"metadata": metadata})


def _sanitize_context_for_sink(items: list[ContextItem]) -> list[ContextItem]:
    guard = SinkGuard()
    sanitized: list[ContextItem] = []
    for item in items:
        redacted_text, redacted = guard.redact(item.content)
        metadata = dict(item.metadata)
        metadata["redacted"] = redacted
        sanitized.append(item.model_copy(update={"content": redacted_text, "metadata": metadata}))
    return sanitized


def _priority_from_name(name: str) -> ContextPriority:
    return ContextPriority[name]


def _project_manifest_summary(manifest: ProjectManifest) -> str:
    technology_profiles = ", ".join(manifest.technology_profiles)
    return (
        f"Project: {manifest.project_name}\n"
        f"Root: {manifest.root}\n"
        f"Profile: {manifest.profile}\n"
        f"Technology profiles: {technology_profiles}\n"
        f"Files: {len(manifest.files)}\n"
        f"Symbols: {len(manifest.symbols)}"
    )


def _provider_policy_summary(config: OpenContextConfig) -> str:
    provider = config.models.default.provider
    allowed = [
        policy
        for policy in config.provider_policies
        if policy.provider == provider and policy.allowed
    ]
    if not allowed:
        return f"Provider policy: {provider} has no allowed policy and must fail closed."
    policy = allowed[0]
    classifications = ", ".join(sorted(policy.allowed_classifications)) or "none"
    external = "enabled" if config.security.external_providers_enabled else "disabled"
    return (
        f"Provider policy: provider={provider}; external_providers={external}; "
        f"allowed_classifications={classifications}; "
        f"require_redaction={policy.require_redaction}."
    )


def _build_spans(state: WorkflowRunState, trace_id: str, root_span_id: str) -> list[TraceSpan]:
    spans = [
        TraceSpan(
            trace_id=trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            name="workflow.run",
            start_time=state.step_results[0].start_time
            if state.step_results
            else datetime.now(tz=UTC),
            end_time=datetime.now(tz=UTC),
            attributes={"workflow.name": state.workflow_name},
        )
    ]
    for step in state.step_results:
        span_name = _step_to_span_name(step.name)
        attributes = {"step.summary": step.summary, "step.duration_ms": step.duration_ms}
        if step.name == "context.pack" and state.context_pack is not None:
            attributes["context.pack.used_tokens"] = state.context_pack.used_tokens
            attributes["context.pack.omissions"] = [
                omission.model_dump(mode="json") for omission in state.context_pack.omissions
            ]
        spans.append(
            TraceSpan(
                trace_id=trace_id,
                span_id=uuid4().hex[:16],
                parent_span_id=root_span_id,
                name=span_name,
                start_time=step.start_time,
                end_time=step.end_time,
                attributes=attributes,
            )
        )
    spans.append(
        TraceSpan(
            trace_id=trace_id,
            span_id=uuid4().hex[:16],
            parent_span_id=root_span_id,
            name="trace.persist",
            start_time=datetime.now(tz=UTC),
            end_time=datetime.now(tz=UTC),
            attributes={"trace.persisted": True},
        )
    )
    return spans


def _step_to_span_name(step_name: str) -> str:
    if step_name == "llm.generate":
        return "llm.generate"
    return step_name


def embeddings_generate(state: WorkflowRunState, services: WorkflowServices) -> str:
    from opencontext_core.embeddings.extractors import items_from_manifest

    if services.embedding_worker is None:
        return "embeddings disabled (no worker configured)"

    manifest = _require_manifest(state)
    items = items_from_manifest(manifest)

    if not items:
        return "no items to embed"

    queued = services.embedding_worker.enqueue_sync(items)
    return f"queued {queued}/{len(items)} items for async embedding"
