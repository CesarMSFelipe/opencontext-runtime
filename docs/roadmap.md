# Roadmap

## Current Status (v0.2.0)

OpenContext Runtime v0.2.0 delivers a complete context engineering platform with:

- **SDD Orchestrator**: Full 8-phase lifecycle (explore → propose → spec → design → tasks → apply → verify → archive) with DAG state tracking, artifact stores (engram/openspec/hybrid), and per-phase model assignment via `SDDProfile`
- **Agent system**: Runtime agent orchestrator with pluggable skill-based agents and subagent spawning
- **LLM provider adapters**: OpenRouter, Anthropic, OpenAI, Local (Ollama), and Mock providers with unified adapter interface
- **Learning system**: Memory usability layer with context-aware retrieval and semantic reranking
- **Quality gates**: 7 built-in CI checks (security, quality, docs, performance, accessibility, dependencies, type safety)
- **Indexing pipeline**: Knowledge graph with SQLite+FTS5, call graph analysis, impact analysis, and framework route detection (19+ languages)
- **Interactive setup wizard**: Guided profiles (minimal, full, agents-only, mcp-only) with post-install verification
- **Security layer**: Secret redaction, provider policy enforcement, context firewall, prompt injection boundaries, air-gapped mode
- **Observability**: OTel-compatible tracing pipeline with metrics and logging
- **Context quality evaluation**: 5-dimension benchmark suite with ContextBench
- **Deep diagnostics**: `opencontext doctor deep` for runtime introspection
- **Plugin ecosystem**: Remote registry, GitHub installs, version pinning, checksum verification
- **Agent installer**: Support for 13+ AI coding agents with auto-detection and config generation
- **Memory layer**: Context repository with progressive disclosure, pinned memory, temporal memory, context DAG, session harvesting

## Next Milestones

1. **Parser-backed dependency graphs**: Deeper symbol extraction with cross-file type resolution and more accurate impact analysis
2. **Public-key workflow-pack signing**: Signed workflow packs with transparency log integration for supply-chain integrity
3. **Production provider SDK packages**: Published provider adapter packages (OpenAI, Anthropic, OpenRouter) outside core as documented extras
4. **Context quality GA**: Production-ready quality gates with configurable thresholds and CI integration
5. **Enterprise hardening**: Multi-user policy enforcement, hosted governance scaffolds, and org baseline distribution

## Not Yet Enterprise Ready

The design is enterprise-oriented, but certification, multi-user policy enforcement, hosted governance, and provider-specific production adapters are not complete. The security layer provides local guardrails and scaffolds that do not make the project a fully certified enterprise platform.
