# Changelog

All notable changes to OpenContext Runtime will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-21

### Added
- Core context engineering runtime with token-efficient packing
- Knowledge graph with SQLite+FTS5, call graph analysis, and impact analysis
- Semantic code search with vector embeddings
- Graph visualization (DOT/Graphviz export)
- Git context enrichment (blame, history, stats)
- Spec-Driven Development (SDD) orchestrator with 7-phase lifecycle
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
