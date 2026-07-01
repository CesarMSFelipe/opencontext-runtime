"""FastAPI adapter for OpenContext Runtime."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from opencontext_api.memory_routes import router as memory_router
from opencontext_api.sdd_routes import router as sdd_router
from opencontext_api.schemas import (
    AgentContextRequest,
    ContextPackRequest,
    ContextPackResponse,
    IndexRequest,
    IndexResponse,
    ManifestResponse,
    OrchestrateRequest,
    PreparedContextRequest,
    PreparedContextResponse,
    RepoMapResponse,
    RunRequest,
    RunResponse,
    ScaffoldResponse,
    SetupRequest,
    SetupResponse,
    TraceResponse,
    ValidateRequest,
    VerifiedContextRequestBody,
    VerifiedContextResponse,
)
from opencontext_core.actions import ActionRequest, ActionType, evaluate_action
from opencontext_core.doctor.checks import run_doctor
from opencontext_core.dx.security_reports import scan_project
from opencontext_core.dx.tokens import build_token_report
from opencontext_core.errors import MemoryStoreError
from opencontext_core.project.profiles import TechnologyProfile
from opencontext_core.retrieval.contracts import RetrievalSurface, VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime
from opencontext_core.safety.redaction import SinkGuard

try:
    from opencontext_profiles import first_party_profiles
except ModuleNotFoundError:

    def first_party_profiles() -> list[TechnologyProfile]:
        return []


app = FastAPI(title="OpenContext Runtime API", version="0.1.0")
app.include_router(memory_router)
app.include_router(sdd_router)


def _runtime() -> OpenContextRuntime:
    return OpenContextRuntime(technology_profiles=first_party_profiles())


@app.exception_handler(MemoryStoreError)
def _memory_store_error(request: Request, exc: MemoryStoreError) -> JSONResponse:
    # A missing trace/manifest is a 404, not an opaque 500.
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.post("/v1/index", response_model=IndexResponse)
def index_project(request: IndexRequest) -> IndexResponse:
    """Index a project root."""
    runtime = _runtime()
    manifest = runtime.index_project(request.root)
    return IndexResponse(
        project_name=manifest.project_name,
        files=len(manifest.files),
        symbols=len(manifest.symbols),
        technology_profiles=manifest.technology_profiles,
    )


@app.post("/v1/setup", response_model=SetupResponse)
def setup_project(request: SetupRequest) -> SetupResponse:
    """Create project harness files and persist the project index without CLI commands."""
    runtime = _runtime()
    result = runtime.setup_project(
        request.root,
        write_config=request.write_config,
        refresh_index=request.refresh_index,
    )
    return SetupResponse(**result.model_dump())


@app.post("/v1/runs", response_model=RunResponse)
def run_workflow(request: RunRequest) -> RunResponse:
    """Run a configured workflow."""
    runtime = _runtime()
    result = runtime.ask(request.input, request.workflow_name)
    safe_answer, _ = SinkGuard().redact(result.answer)
    return RunResponse(
        answer=safe_answer,
        trace_id=result.trace_id,
        token_usage=result.token_usage,
        selected_context_count=result.selected_context_count,
    )


@app.get("/v1/traces/{trace_id}", response_model=TraceResponse)
def get_trace(trace_id: str) -> TraceResponse:
    """Load a persisted trace."""
    runtime = _runtime()
    trace = runtime.load_trace(trace_id)
    return TraceResponse(trace=trace.model_dump(mode="json"))


@app.get("/v1/project/manifest", response_model=ManifestResponse)
def get_manifest() -> ManifestResponse:
    """Load the persisted project manifest."""
    runtime = _runtime()
    manifest = runtime.load_manifest()
    return ManifestResponse(manifest=manifest.model_dump(mode="json"))


@app.get("/v1/project/repomap", response_model=RepoMapResponse)
def get_repo_map() -> RepoMapResponse:
    """Render the compact repository map."""
    runtime = _runtime()
    safe_repo_map, _ = SinkGuard().redact(runtime.render_repo_map())
    return RepoMapResponse(repo_map=safe_repo_map)


@app.post("/v1/context/pack", response_model=ContextPackResponse)
def build_context_pack(request: ContextPackRequest) -> ContextPackResponse:
    """Build a token-aware context pack."""
    runtime = _runtime()
    pack = runtime.build_context_pack(request.query, request.max_tokens)
    return ContextPackResponse(pack=pack.model_dump(mode="json"))


@app.post("/v1/context", response_model=PreparedContextResponse)
def prepare_context(request: PreparedContextRequest) -> PreparedContextResponse:
    """Prepare and persist a compact context bundle for non-CLI callers."""
    runtime = _runtime()
    prepared = runtime.prepare_context(
        request.query,
        root=request.root,
        max_tokens=request.max_tokens,
        refresh_index=request.refresh_index,
    )
    safe_context, _ = SinkGuard().redact(prepared.context)
    return PreparedContextResponse(
        trace_id=prepared.trace_id,
        context=safe_context,
        included_sources=prepared.included_sources,
        omitted_sources=prepared.omitted_sources,
        token_usage=prepared.token_usage,
        trust_decision=prepared.trust_decision,
        fallback_actions=prepared.fallback_actions,
        source_surfaces=prepared.source_surfaces,
    )


@app.post("/v1/context/verify", response_model=VerifiedContextResponse)
def verify_context(request: VerifiedContextRequestBody) -> VerifiedContextResponse:
    """One-shot verified context: gates, trust, risk, and a persisted trace.

    Surface parity with the CLI: the same gated/verified pipeline, not the raw
    ungated context that /v1/context/pack and /v1/context return.
    """
    runtime = _runtime()
    result = runtime.verify_context(
        VerifiedContextRequest(
            query=request.query,
            root=Path(request.root) if request.root else None,
            max_tokens=request.max_tokens,
            refresh_index=request.refresh_index,
            include_memory=request.include_memory,
            include_vector=request.include_vector,
        )
    )
    safe_context, _ = SinkGuard().redact(result.context)
    return VerifiedContextResponse(
        trace_id=result.trace_id,
        context=safe_context,
        evidence=[item.model_dump(mode="json") for item in result.evidence],
        memory=[item.model_dump(mode="json") for item in result.memory],
        gates=[gate.model_dump(mode="json") for gate in result.gates],
        risk_level=result.risk_level.value,
        trust_decision=result.trust_decision.model_dump(mode="json"),
        token_usage=result.token_usage,
        omitted_sources=result.omitted_sources,
    )


@app.get("/v1/security/report")
def security_report() -> dict[str, object]:
    return {"status": "scaffold", "result": scan_project().model_dump()}


@app.post("/v1/security/scan")
def security_scan() -> dict[str, object]:
    return {"status": "scaffold", "result": scan_project().model_dump()}


@app.get("/v1/doctor")
def doctor() -> dict[str, object]:
    runtime = _runtime()
    return {"checks": [check.model_dump() for check in run_doctor(runtime.config)]}


@app.get("/v1/tokens/report")
def tokens_report() -> dict[str, object]:
    # Use the configured project root for parity with the other routes (was the
    # server CWD, which differs from where the project is actually indexed).
    runtime = _runtime()
    return build_token_report(Path(runtime.config.project_index.root)).model_dump()


@app.post("/v1/orchestrate", response_model=ScaffoldResponse)
def orchestrate(request: OrchestrateRequest) -> ScaffoldResponse:
    """Plan a permissioned orchestration run without executing actions."""
    runtime = _runtime()
    mode = runtime.config.security.mode
    return ScaffoldResponse(
        status="scaffold",
        result={
            "mode": "orchestrate",
            "requirements_path": request.requirements_path,
            "safe_commands": evaluate_action(
                ActionRequest(action=ActionType.RUN_SAFE_COMMAND),
                security_mode=mode,
            ).model_dump(mode="json"),
            "write_file": evaluate_action(
                ActionRequest(action=ActionType.WRITE_FILE),
                security_mode=mode,
            ).model_dump(mode="json"),
        },
    )


@app.post("/v1/validate", response_model=ScaffoldResponse)
def validate(request: ValidateRequest) -> ScaffoldResponse:
    """Plan safe validation checks without running shell commands."""
    runtime = _runtime()
    mode = runtime.config.security.mode
    return ScaffoldResponse(
        status="scaffold",
        result={
            "profile": request.profile,
            "run_tests": evaluate_action(
                ActionRequest(action=ActionType.RUN_TEST),
                security_mode=mode,
            ).model_dump(mode="json"),
            "run_linter": evaluate_action(
                ActionRequest(action=ActionType.RUN_LINTER),
                security_mode=mode,
            ).model_dump(mode="json"),
        },
    )


@app.post("/v1/agent-context", response_model=ScaffoldResponse)
def agent_context(request: AgentContextRequest) -> ScaffoldResponse:
    """Return a sanitized generic agent context envelope."""
    runtime = _runtime()
    prepared = runtime.prepare_context(
        request.query,
        root=request.root,
        max_tokens=request.max_tokens,
        refresh_index=request.refresh_index,
        surface=RetrievalSurface.AGENT_TOOL,
    )
    safe_query, _ = SinkGuard().redact(prepared.query)
    safe_context, _ = SinkGuard().redact(prepared.context)
    return ScaffoldResponse(
        status="ready",
        result={
            "target": request.target,
            "mode": request.mode,
            "max_tokens": request.max_tokens,
            "trace_id": prepared.trace_id,
            "query": safe_query,
            "context": safe_context,
            "included_sources": prepared.included_sources,
            "omitted_sources": prepared.omitted_sources,
            "token_usage": prepared.token_usage,
            "trust_decision": prepared.trust_decision,
            "fallback_actions": prepared.fallback_actions,
            "source_surfaces": prepared.source_surfaces,
            "raw_secrets_included": False,
        },
    )


@app.post("/v1/refactor/sdd", response_model=ScaffoldResponse)
def sdd_flow(request: PreparedContextRequest) -> ScaffoldResponse:
    """Specification-Driven Development (SDD) context engineering flow.

    Unified workflow for context preparation across all technology stacks.
    Implements the SDD flow: explore → propose → test → verify → review.

    This endpoint is technology-agnostic and works with any framework,
    language, or architecture pattern. It integrates with OpenContext's
    agent-agnostic workflow engine to provide consistent context preparation
    regardless of the underlying technology.
    """
    runtime = _runtime()

    # Explore - retrieve and rank candidates
    prepared = runtime.prepare_context(
        request.query,
        root=request.root,
        max_tokens=request.max_tokens,
        refresh_index=request.refresh_index,
        surface=RetrievalSurface.WORKFLOW,
    )

    safe_query, _ = SinkGuard().redact(prepared.query)
    safe_context, _ = SinkGuard().redact(prepared.context)

    # Test - validate context pack safety
    from opencontext_core.models.context import ContextItem, ContextPriority
    from opencontext_core.safety.firewall import ContextFirewall

    firewall = ContextFirewall(runtime.config)
    # The firewall guards content, not paths: wrap the prepared (already-redacted)
    # context as one item so the export gate inspects real text, not source names.
    export_item = ContextItem(
        id="sdd-test-context",
        content=prepared.context,
        source="prepared_context",
        source_type="aggregate",
        priority=ContextPriority.P2,
        tokens=0,
        score=0.0,
    )
    test_decision = firewall.check_context_export([export_item], sink="sdd_test")

    # Verify - security scan
    scan = scan_project(request.root)

    # Review - check for high-risk patterns
    manifest = runtime.load_manifest()
    high_risk_count = sum(
        1
        for f in manifest.files
        if any(s in f.path.lower() for s in ["secret", "key", "credential", "token", "password"])
    )

    return ScaffoldResponse(
        status="completed",
        result={
            "mode": "sdd",
            "trace_id": prepared.trace_id,
            "query": safe_query,
            "context": safe_context,
            "included_sources": prepared.included_sources,
            "omitted_sources": prepared.omitted_sources,
            "token_usage": prepared.token_usage,
            "trust_decision": prepared.trust_decision,
            "fallback_actions": prepared.fallback_actions,
            "source_surfaces": prepared.source_surfaces,
            "raw_secrets_included": False,
            "safety": {
                "test_allowed": test_decision.allowed,
                "test_reason": test_decision.reason,
                "security_scan_severity": "high" if scan.findings else "none",
                "security_findings": len(scan.findings),
                "high_risk_files": high_risk_count,
                "review_status": "approved" if high_risk_count == 0 else "requires_review",
            },
        },
    )
