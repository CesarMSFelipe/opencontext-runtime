# Changelog

All notable changes to OpenContext Runtime will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-25

### Added

- **Harness Runner**: Full workflow execution engine with phase governance, token budget enforcement (off/warn/strict), and gate evaluation. Pre-built workflows: `sdd`, `explore-only`, `apply-only`. Results persisted to `.opencontext/runs/<run_id>/`.
- **SDD Context Builder**: Auto-detects TDD capabilities from project structure and generates `.opencontext/sdd/context.json` with per-phase token budgets and orchestrator profiles.
- **Onboarding Service**: One-command project setup via `opencontext install`. Sets up workspace, indexes the knowledge graph, configures SDD/TDD context, generates agent contracts, and installs harness workflows.
- **Config Wizard TUI**: `opencontext config wizard` now opens an interactive Rich menu with options for full configuration, security settings, feature toggles, token budgets, agent integrations, and plugins.
- **Agent Registry**: Manages AI client integrations (OpenCode, Cursor, Claude Code, Aider, etc.) with auto-detection and install capabilities.
- **New Adapters**: `AiderAdapter` for Aider AI integration and `LocalAdapter` for direct local subprocess execution (no API dependencies).
- **Agent Manifest Generation**: Auto-generates `.opencontext/agents/<client>.md` contract files with TDD context and harness instructions per agent.
- **Homebrew and npm/pnpm Installation**: Added installation methods for macOS (Homebrew) and Node.js (npm/pnpm) environments.
- **Enhanced CLI**: First-run detection, inline hints after commands, `--yes` flag for non-interactive setup, and step-by-step install progress with Rich Status spinners.
- **Config Set/Get Expanded**: Dot-notation paths for nested settings (e.g., `features.knowledge_graph`, `sdd.tdd_mode`, `agents.active_clients`).

### Changed

- **`onboard` renamed to `install`**: All references updated across code, docs, and CLI. `opencontext onboard` still works for backward compatibility but redirects to `install`.
- **`==SUPPRESS==` bug fixed**: Replaced `argparse.SUPPRESS` with custom `_DeprecationAwareParser` to fix Python 3.12 `--help` output bug.
- **Deprecated commands show clear errors**: `run`, `orchestrate`, `validate`, `propose`, `governance`, `evidence` now return exit code 2 with migration hints instead of dispatching to removed handlers.
- **SDD commands deprecated**: `opencontext sdd explore`, `propose`, `apply`, `test`, `verify`, `review`, `archive`, `up-code`, and `flow` emit deprecation warnings and delegate to `harness run`.
- **ASCII-safe CLI output**: Replaced Unicode arrows (`→`) with ASCII (`->`) in all `print()` and argparse output for Windows terminal compatibility.

### Fixed

- **Ruff lint violations**: All 44 violations across packages resolved (undefined names, unused variables, ambiguous variable names, line too long, unused imports).
- **Ruff format**: All packages and tests reformatted for consistency.
- **Mypy type errors**: Fixed generic list type annotation and conditional import.
- **Test suite**: 611 tests passing, 0 failures. New test coverage for harness, onboarding, adapters, CLI smoke, agent registry, and graph tunnel.

### Docs

- README restructured for quick adoption with clear value proposition and installation paths.
- Updated guides: `getting-started-guide.md`, `five-minute-setup.md` with `install` references.
- SDD workflow documentation updated for harness runner architecture.
- Added installation experience and SDD/TDD gap analysis.

## [0.2.1-beta] - 2026-05-22

### Added
- **Harness runner governance**: Budget enforcement (off/warn/strict) for all workflow phases
- **Phase gates**: Gate evaluation per phase (project index, context pack, budget, persistence)
- **Run artifact persistence**: Runs saved to `.opencontext/runs/<run_id>/` with ledgers, gates, artifacts, proposals, apply manifests, verify reports, and reviews
- **Per-phase budget limits**: Explore 6K, propose 6K, apply 6K, verify 4K, review 4K, archive 2K
- **Explore-only workflow**: Lightweight `harness run --workflow explore-only` for indexing + context pack
- **JSON output mode**: `harness run --json` for CI integration
- **Health checks**: `opencontext verify` now reports 6/6 harness phases, runner status, adapter status, boundary service status

### Changed
- **SDD commands deprecated**: `opencontext sdd explore`, `propose`, `apply`, `test`, `verify`, `review`, `archive`, `up-code`, and `flow` now emit deprecation warnings and delegate to `harness run`
- **`sdd flow` delegates to HarnessRunner**: Invokes `harness run --workflow sdd` with TDD context setup
- **Help text**: All deprecated SDD subcommands marked with `[DEPRECATED]` and migration hint in `--help`

### Fixed
- **publish.yml**: Switch from PyPI API token to Trusted Publishing for secure automated releases
- **Version bumps**: All 5 packages synced to 0.2.1b0 for pre-release consistency

### Docs
- README: SDD section rewritten for harness runner (6 governance phases, token budgets, health checks)
- docs/workflows/sdd-workflow.md: complete rewrite matching harness runner architecture (6 phases, gates, artifact structure, migration table)
- docs/workflows/sdd-implementation-summary.md: updated CLI commands, workflow composition, and references to use `harness run`
- docs/product/community-sdd-tdd-gap-analysis.md: updated `sdd flow` references to `harness run`
- docs/getting-started/getting-started-guide.md: updated SDD workflow section for harness commands

## [0.2.0] - 2026-05-22

### Added
- **SDD Orchestrator**: Full 8-phase Spec-Driven Development lifecycle (explore → propose → spec → design → tasks → apply → verify → archive)
- **SDD profile management**: Per-phase model assignment with provider routing
- **Agent system**: Runtime agent orchestrator with pluggable skill-based agents and subagent spawning
- **Agent installer**: Detect and install 13+ AI coding agents (Claude Code, OpenCode, Cursor, Codex, Windsurf, etc.)
- **LLM provider adapters**: OpenRouter, Anthropic, OpenAI, Local (Ollama), and Mock providers with unified interface
- **Learning system**: Memory usability layer with context-aware retrieval and semantic reranking
- **Quality gates**: CI check system with 7 built-in checks (security, quality, docs, performance, accessibility, dependencies, type safety)
- **Interactive setup wizard**: Guided profiles (minimal, full, agents-only, mcp-only) with post-install verification
- **Full indexing pipeline**: Knowledge graph (SQLite+FTS5), call graph analysis, impact analysis, semantic search
- **Context observability**: OTel-compatible tracing pipeline with metrics and logging
- **Context quality benchmark**: 5-dimension scoring (relevance, completeness, freshness, efficiency, safety)
- **Deep diagnostics**: `opencontext doctor deep` for runtime introspection
- **LLM context firewall**: Transparent proxy with secret redaction, provider policy enforcement, and egress controls
- **DX hints**: `.opencontexthints`, `AGENTS.md`, `CLAUD.md` support with call budget tracking
- **Plugin system**: Command and hook registry with GitHub and direct URL installs
- **Cross-platform config**: Windows `%APPDATA%`, Linux/macOS `~/.config` with auto-migration
- **Demo project**: Reference project with auth, models, services, and tests
- **Shell completions**: bash, zsh, fish support

### Fixed
- CI pipeline now passes at 100% across ruff, mypy, and pytest on both Linux and Windows
- 60+ mypy type errors resolved across 18 files (type annotations, API mismatches, undefined names, missing type args)
- Agent source files tracked in git (removed from `.gitignore` after initial scaffolding oversight)
- `CallGraphAnalyzer` API mismatches: `max_depth` → `depth`, `get_impact_radius` → `analyze`
- `ImpactAnalyzer` constructor now correctly receives `db` parameter
- Cross-platform `sys.platform` branching avoids mypy unreachable-code warnings
- Type stubs (`types-PyYAML`, `types-requests`) installed in CI for mypy

### Changed
- Complete codebase cleanup: ruff lint formatting, import sorting, `Optional[X]` → `X | None`
- Core refactoring across runtime, config, and operating model modules
- Documentation updated for all new features

[0.2.0]: https://github.com/CesarMSFelipe/OpenContext-Runtime/releases/tag/v0.2.0

## [0.1.0] - 2026-05-22

### Added
- Core context engineering runtime with token-efficient packing
- Knowledge graph with SQLite+FTS5, call graph analysis, and impact analysis
- Semantic code search with vector embeddings
- Graph visualization (DOT/Graphviz export)
- Git context enrichment (blame, history, stats)
- Spec-Driven Development (SDD) orchestrator with 8-phase lifecycle
- SDD profile management for per-phase model assignment
- Skill registry with auto-discovery and compact rules
- Agent installer supporting 13+ AI coding agents (Claude Code, OpenCode, Cursor, Codex, Windsurf, etc.)
- MCP server with 8 tools for agent integration
- Interactive TUI (prompt_toolkit-based)
- CI check system with 7 built-in checks (security, quality, docs, performance, accessibility, dependencies, type safety)
- Agent hints system (.opencontexthints, AGENTS.md, CLAUDE.md support)
- LLM provider adapters (OpenRouter, Anthropic, OpenAI, Local/Ollama, Mock)
- Performance metrics tracking (tokens, timing, costs)
- Plugin system with command and hook registry
- Interactive installation wizard with profiles (minimal, full, agents-only, mcp-only)
- One-liner installer (curl|bash) + Windows PowerShell installer
- Shell completions (bash, zsh, fish)
- Demo project with auth, models, services, and tests
- Comprehensive documentation and getting started guide

### DX & Health
- **State tracking**: `~/.config/opencontext/state.json` tracks components, plugins, versions, operation timestamps
- **Post-install verification**: `opencontext verify` with 7 health checks, rich output, and `--json` for CI
- **Self-update**: `opencontext update` checks PyPI (24h cache), `opencontext upgrade` installs latest
- **Config backup & rollback**: Auto-backup before every config change. `opencontext config backup/backups/restore/cleanup`
- **Interactive plugin wizard**: `opencontext config reconfigure plugins` and wizard Step 5 now let you browse and install plugins with y/n prompts

### Plugin Ecosystem (Extended)
- **Remote registry** with built-in fallback (3 plugins), 1-hour cache
- **GitHub installs**: `opencontext plugin install <name> --github owner/repo`
- **Direct URL installs**: `opencontext plugin install <name> --url <url>` (tar.gz/zip)
- **Auto-update**: `opencontext plugin update` checks registry for newer versions
- **Version pinning**: `opencontext plugin install <name> --ver 0.1.0`
- **Plugin info**: `opencontext plugin info <name>` shows full metadata
- **Rollback on failure**: Auto-backup before install/remove, restore on error
- **Checksum verification**: SHA-256 verification when available
- **Idempotent installs**: Reinstalling same version is a safe no-op
- **State tracking**: Plugins tracked in `state.json` with source metadata

### Security
- Zero-trust defaults: tools off, MCP off, external providers off
- Secret redaction before prompts, traces, cache, and memory
- Air-gapped mode for offline operation
- Provider policy enforcement
- Prompt injection boundaries
- Egress policy controls

[0.1.0]: https://github.com/CesarMSFelipe/OpenContext-Runtime/releases/tag/v0.1.0
