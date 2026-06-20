# Changelog

All notable changes to OpenContext Runtime will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-06-20

### Added

- **Co-resident Engram coexistence**: when an Engram install is present, OpenContext routes the EPISODIC/SEMANTIC memory layers to it (read via its SQLite, write via the `engram` CLI) and keeps the other layers local; with no Engram the local store covers every layer. Auto-detection is suppressed under pytest. Memory still defaults to local — Engram is opt-in.
- **Real local embeddings**: `OllamaEmbeddingGenerator` produces embeddings from a co-resident Ollama over stdlib HTTP (no new dependency); semantic memory recall is wired when `embedding.enabled`.
- **Per-role model routing via MCP sampling**: the model each role uses is delivered to the host agent as an MCP `sampling/createMessage` `modelPreferences.hints`, and `opencontext models set-role` writes `models.roles.<role>.model`.
- **In-process agentic run**: the `opencontext_run` MCP tool drives the SDD harness using the host client's selected model through the sampling transport.
- **`uninstall --purge`**: removes managed blocks and clears install state, with a dry-run preview.
- **Plugin permissions manifest**: a deny-by-default permissions manifest is enforced at plugin load.

### Changed

- `standard` workflow track now includes `propose` — `spec`/`design` require the proposal artifact, so the track is runnable end to end.
- Non-interactive `install --yes` wires the agents actually detected on the machine instead of defaulting to a single client.
- Documentation and CLI help corrected to match shipped behavior (14 MCP tools, seven personas, the `oc-onboard` skill, the real `explore → … → verify → review → archive` phase flow). No unverified claims.

### Fixed

- **Secret redaction**: the full body of a PEM private key is now redacted (the body after the header was leaking).
- **FTS scoring**: relevance is position-based (the previous score was inverted).
- **Docstring extraction**: tree-sitter docstrings are extracted correctly (were always empty).
- **Code compression**: comment/docstring stripping is string-aware — a `#` or `//` inside a string literal no longer truncates the line, and triple-quoted *data* strings are preserved.
- **Profile detection**: node/react/next/rust/drupal require a real manifest, so a generic `src/` layout is no longer mislabeled (e.g. a Python project tagged "node").
- **`opencontext update`**: tolerates PEP 440 pre-release versions (it was crashing and silently hiding every update) and no longer reports a stale cached version that contradicts `--version`.
- **Dependency graph**: Python relative imports (`from .x import y`) now resolve to internal edges.
- **Context export**: redact-and-continue at the export sink — every REDACT-policy finding is removed, not just the first.
- **`verify`**: honest exit code; tests are scoped to changed files instead of running the whole suite for a verify report.
- **Model routing**: per-role/per-phase routing reaches the executor by routing onto a copy, without mutating the caller's request.

### Security

- Credit-card detection is gated by the Luhn checksum; the context firewall honors the REDACT policy for secrets and prompt-injection; the firewall proxy no longer echoes secrets on a blocked POST.

## [1.2.0] - 2026-06-18

### Performance

- **FTS5 rebuild deferred**: `upsert_nodes()` no longer calls `INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')` per file. A single `rebuild_fts()` call runs after the full indexing loop. Benchmark: 624 Python files 96 s → 5 s (19×).

### Added

- **Incremental watch mode**: `WatchService` passes `set[str] | None` to the index callback — a set for incremental re-index, `None` for full rebuild. `_watch()` in the CLI uses `rt.reindex_files()` for changed paths.
- **Context artifacts**: Non-code files (SQL schemas, OpenAPI specs, ADRs) declared under `context_artifacts` in `opencontext.yaml` are indexed as `kind='artifact'` nodes, searchable through all MCP tools.
- **`opencontext_files` summarize mode**: `summarize=true` returns directory-level aggregates (file count, symbol count, language breakdown) instead of the full file list — reduces token usage on large repos.
- **Memory `topic_key` + dedup**: `MemoryRecord` gains `topic_key` (hierarchical handle like `architecture/auth-model`) and `revision_count`. `store_by_topic_key()` upserts in-place instead of creating duplicates.
- **Contradiction detection wired**: `ContradictionDetector` is now called inside `store()` — flags records with same key, different content, and confidence delta > 0.3.
- **`skill list` and `skill-registry list` commands**: List available skills from registry and agent skill dirs.
- **Per-phase model config**: `ModelConfigMap.phases` dict allows per-phase model overrides (explore, spec, design, tasks, apply, verify, review, archive, judgment).
- **Judgment-day phase**: Adversarial review phase (`judgment`) with BLOCKER/SHOULD_FIX/APPROVED verdicts; GGA rules enforcement; `clarify` command.
- **Quality workflow tracks**: `quick`, `standard`, `full`, `full+judgment`, `full+gga` harness tracks.
- **Skill registry v2**: `.skill.md` scanner alongside legacy `SKILL.md`/frontmatter format; built-in skills (fix, prd, work-unit-commits, oc-onboard).
- **Trae/Hermes agent support**: Detected and configured by `AgentInstaller`.
- **`verify --json` `ok` field**: Each check entry now includes `"ok": bool` for CI consumers.
- **`security scan --json` `files_scanned`**: Field now populated with the actual count.
- **Content snippet in FTS5**: Symbol body indexed for semantic search via `content_snippet`.
- **Memory harvest enabled by default**: Auto-approves low-stakes candidates after apply.

### Fixed

- `skill list` / `skill-registry list` — `invalid choice` error (subcommands were missing).
- `F821` undefined `args` in `_onboard` — replaced `getattr(args, "root", ".")` with `root`.
- Import order `E402` in `memory/stores.py` and `skills/registry.py`.
- Mypy: `dict[str, str]` annotation, `Path` param type, unused `type: ignore`, removed unreachable guard in `reindex_files`.
- Watch service callback signature updated to accept `changed: set[str] | None`.
- Tests calling `upsert_nodes()` now call `rebuild_fts()` explicitly after bulk inserts.
- README MCP tool count assertion accepts `"13 MCP tools"` substring.
- Worktrees excluded from KG indexing and security scans.
- `demo` re-index skip; `security scan --json`; `bytecode inspect` fallback.

## [1.0.0] - 2026-05-28

### Fixed

- **`doctor` after fresh install**: `_runtime()` now passes `None` config when `opencontext.yaml` is absent, falling back to defaults instead of raising `ConfigurationError`.
- **"First Run" banner loop**: `is_first_run()` now treats `.opencontext/sdd/context.json` as a setup marker so the welcome banner does not reappear after `opencontext install`.
- **Menu install action**: `_run_install()` now clears the screen before invoking the install wizard (header was only shown on error).
- **Deprecated CLI commands**: Removed `sdd`, `check`, `packs`, `cost`, `policy`, `drupal`, `ddev` top-level commands. All are now in `_DeprecationAwareParser._DEPRECATED` and exit 2 with a migration message.
- **Deprecated subcommands**: Removed `eval security`, `checkpoint diff`, `checkpoint inspect`, `workflow dry-run`, `workflow explain`, `cache explain`, `org baseline create`, `release transparency`, `security report`, `security policy`, `workflows run`.
- **Stub functions**: Removed `_sdd`, `_sdd_*`, `_check`, `_drupal`, `_ddev`, `_cost`, `_policy`, `_workflow`, `_context_dag`.

### Added

- **D3 knowledge graph viewer**: `opencontext knowledge-graph view` now saves an interactive `opencontext-kg-view.html` with a zoomable/pannable D3 tree and opens it in the browser automatically.
- **Ecosystem update checker**: `EcosystemUpdateChecker` tracks updates for companion packages (e.g. engram). Notices appear in the TUI menu update banner and after `opencontext upgrade`.
- **Cross-file call edges**: `KnowledgeGraph.index_project()` now runs a second-pass resolver that links call edges whose source and target live in different files.
- **Pack telemetry**: `opencontext pack` automatically records a `TelemetryEvent` so token-reduction stats accumulate without needing a separate benchmark run.
- **Clipboard fallback**: `pack --copy` now tries `xclip`, `xsel`, `wl-copy`, and `pbcopy` directly via subprocess before giving up, with an actionable install hint on failure.
- **Global MCP setup on install**: `opencontext install` now calls `AgentInstaller` to write `~/.config/opencode/mcp.json` and `~/.config/opencode/agents/sdd-orchestrator.json`.
- **Verify phase in install**: Install ends with a health-check step that reports `N/N checks passed` before finishing.
- **README**: Added `memory` and `agent-context` sections to CLI Reference.
- **TUI menu**: Added option 11 "Context memory" to the Development section of the main TUI menu.
- **Tests**: New test files `tests/core/test_backup.py`, `tests/core/test_compat.py`, `tests/core/test_errors.py`.

### Changed

- **TUI menu redesign**: Main menu now renders three side-by-side panels (Setup / Configure / Tools) with an inline update notice when cached updates are available.
- **Setup wizard step indicators**: Interactive setup flow shows `● ○ ○` progress dots and clears the screen between steps.
- **`update` hint after commands**: Post-command update notice now also includes outdated ecosystem packages from cache.
- **`_cache()`**: Removed `cache explain` scaffold branch; `cache plan` and `cache warm` remain fully functional.
- **`_release()`**: Removed `release transparency` scaffold JSON fallback; `release audit`, `release gate`, and `release evidence` remain.
- **`_org()`**: `org baseline create` now raises `OpenContextError`; only `org baseline check` remains.
- **`_checkpoint()`**: Non-`create` actions now call `_unreachable`.
- **`_workflows()`**: `workflows run` removed; `list` and `inspect` remain.
- **`_eval()`**: `eval security` branch removed.
- **`_prompt()` export**: Removed misleading `"status": "scaffold"` key from JSON output.

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
