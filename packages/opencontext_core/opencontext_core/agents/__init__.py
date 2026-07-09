"""Agent subsystem for OpenContext Runtime.

The legacy in-process "agent SDK" (BaseAgent / AgentOrchestrator and the five
concrete agents) was removed for the 2.0 cut — it had no live readers. The live
surface now lives in focused submodules that callers import directly:

- ``opencontext_core.agents.executor`` — the agent executor spine
- ``opencontext_core.agents.artifact_store`` — SDD artifact persistence
- ``opencontext_core.agents.sdd_orchestrator`` — the module-level
  ``WORKFLOW_TRACKS`` / ``PHASE_ORDER`` / ``PHASE_DEPENDENCIES`` tables and the
  ``phase_required_harnesses`` helper consumed by the harness runner + explain
- ``opencontext_core.agents.template_renderer`` — phase contract rendering
- ``opencontext_core.agents.sdd_guardrails`` — phase guardrail evaluation

Import those submodules directly; this package no longer re-exports anything.
"""
