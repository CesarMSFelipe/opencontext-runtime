"""Unified onboarding service for project initialization.

Orchestrates workspace creation, config generation, user preferences,
project indexing, SDD/TDD context, agent instruction files, harness
configuration, and MCP setup in a single pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.paths import StorageMode, resolve_workspace_path

# Used only as the fallback when no agent CLI is detected on the host. Detection
# (below) is preferred — we configure what is actually present, not a fixed list.
_FALLBACK_CLIENTS: tuple[str, ...] = ("opencode",)


def default_active_clients() -> list[str]:
    """Agent clients to configure when the caller did not specify any.

    Detects the agent CLIs actually present on this host — Claude Code (``~/.claude``),
    OpenCode, Cursor, Codex, etc. — by the presence of each agent's config dir, the
    same signal the live installer's detector uses. Every detected agent is configured.
    This is why a default ``opencontext install`` on a machine with Claude Code now
    writes its MCP entry, persona files, and permissions with no extra flags, instead
    of the old hard-coded ``["opencode"]`` that silently skipped every other agent.

    Uses :meth:`Configurator.detect_installed` (a pure read of ``~`` — it creates no
    directories), so calling it at ``OnboardingOptions`` construction has no side
    effects. Falls back to :data:`_FALLBACK_CLIENTS` only when nothing is detected (or
    detection raises), so a bare project still gets a sane baseline.
    """
    try:
        from opencontext_core.configurator.service import Configurator

        clients = Configurator().detect_installed()
        if clients:
            return clients
    except Exception:
        pass
    return list(_FALLBACK_CLIENTS)


@dataclass
class OnboardingOptions:
    """Configuration options for the onboarding process."""

    root: Path
    template: str = "generic"
    security_mode: str = "private_project"
    # Default to whatever agent CLIs are actually installed (detected), so a no-flag
    # install configures Claude Code et al. out of the box; opencode-only fallback.
    active_clients: list[str] = field(default_factory=default_active_clients)
    tdd_mode: str = "ask"
    # 'default' = the client's selected model for every phase (no surprise model
    # picks); presets (cheap/hybrid/premium) route per phase, tunable per persona.
    sdd_model_profile: str = "default"
    orchestrator_profile: str = "multi-phase"
    memory_provider: str = "auto"
    setup_mcp: bool = False
    force_agent_files: bool = False
    token_budget_per_phase: int | None = None
    # When True (--scope workspace), write ONLY repo-local files. No writes under
    # $HOME: no global agent config, no user-prefs store, no home backups.
    workspace_only: bool = False


@dataclass
class OnboardingResult:
    """Result of a completed onboarding process."""

    root: str
    config_path: str = ""
    indexed_files: int = 0
    indexed_symbols: int = 0
    knowledge_graph_nodes: int = 0
    knowledge_graph_edges: int = 0
    active_clients: list[str] = field(default_factory=list)
    generated_agent_files: list[str] = field(default_factory=list)
    sdd_context_path: str = ""
    harness_config_path: str = ""
    mcp_configured: bool = False
    warnings: list[str] = field(default_factory=list)


def _normalize_security_mode(mode: str) -> str:
    """Coerce a security-mode string to an exact ``SecurityMode`` enum value.

    Accepts hyphenated legacy aliases (e.g. ``air-gapped``) and falls back to
    ``private_project`` for anything unrecognised, so the written config always
    loads. Invalid values are never passed through verbatim.
    """
    from opencontext_core.config import SecurityMode

    candidate = (mode or "").strip().replace("-", "_").lower()
    try:
        return SecurityMode(candidate).value
    except ValueError:
        return SecurityMode.PRIVATE_PROJECT.value


class OnboardingService:
    """Orchestrates project onboarding: workspace, config, prefs, index, SDD, agents, harness."""

    def run(self, options: OnboardingOptions) -> OnboardingResult:
        """Execute the full onboarding pipeline."""
        from opencontext_core.config import SecurityMode, default_config_data
        from opencontext_core.sdd_runtime import write_sdd_context
        from opencontext_core.user_prefs import UserConfigStore, mark_setup_complete
        from opencontext_core.workspace.layout import ensure_workspace

        root = options.root.resolve()
        result = OnboardingResult(root=str(root))
        sdd_token_budget = options.token_budget_per_phase or 3000

        # 1. Ensure workspace exists
        ensure_workspace(root)

        # 2. Create config if not exists
        config_path = root / "opencontext.yaml"
        if not config_path.exists():
            import yaml

            config_data = default_config_data()
            project = config_data.get("project")
            if isinstance(project, dict):
                project["name"] = root.name or project.get("name", "my-project")
            security = config_data.get("security")
            if isinstance(security, dict):
                security["mode"] = _normalize_security_mode(options.security_mode)
            if options.template == "enterprise":
                security = config_data.get("security")
                if isinstance(security, dict):
                    security["mode"] = SecurityMode.ENTERPRISE.value
                for policy in config_data.get("provider_policies", []):
                    if isinstance(policy, dict) and policy.get("provider") != "mock":
                        policy["allowed"] = False
            # Accept both the enum-aligned 'air_gapped' and the legacy
            # hyphenated 'air-gapped' template name.
            if options.template in ("air-gapped", "air_gapped"):
                security = config_data.get("security")
                if isinstance(security, dict):
                    security["mode"] = SecurityMode.AIR_GAPPED.value
                    security["external_providers_enabled"] = False
                cache = config_data.get("cache")
                if isinstance(cache, dict):
                    semantic = cache.get("semantic")
                    if isinstance(semantic, dict):
                        semantic["enabled"] = False
            # Memory backend: the wizard's explicit choice. Air-gapped forces local
            # (no external coupling); otherwise honor the selected provider.
            memory = config_data.get("memory")
            if isinstance(memory, dict):
                if options.template in ("air-gapped", "air_gapped"):
                    memory["provider"] = "local"
                else:
                    memory["provider"] = options.memory_provider
            config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")
        result.config_path = str(config_path)

        # 2b. Keep the local index/memory out of git. Only write the .gitignore
        # block when storage.mode=local (in-repo layout) or legacy in-repo dirs
        # are detected (upgrading an existing repo). In user mode (default XDG),
        # no in-repo state is written so the .gitignore block is unnecessary.
        # Best-effort — never fail onboarding over it.
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.paths import detect_legacy

            _oc = load_config_or_defaults(config_path)
            # Write .gitignore block only when in-repo state will be written:
            # mode=local explicitly, or legacy dirs already exist in the repo.
            # mode=user (default): state goes to XDG, so no .gitignore entry needed.
            _write_gitignore = (
                _oc.storage.mode == StorageMode.local or detect_legacy(root) is not None
            )
        except Exception:
            _write_gitignore = True  # safe default: write block when uncertain
        if _write_gitignore:
            self._write_gitignore_storage_block(root)
        # NOTE: In mode=user the .storage/ and .opencontext/ dirs are NOT created
        # in the project repo; the runtime writes to XDG state dirs instead.

        # 3. Save user preferences
        store = UserConfigStore()
        prefs = store.load()
        # Normalize here too: prefs must never hold a value the config rejected,
        # otherwise prefs and the written config disagree on the security mode.
        prefs.security_mode = _normalize_security_mode(options.security_mode)
        prefs.sdd.tdd_mode = options.tdd_mode
        prefs.sdd.sdd_model_profile = options.sdd_model_profile
        prefs.sdd.orchestrator_profile = options.orchestrator_profile
        prefs.agents.active_clients = options.active_clients
        prefs.agents.default_client = (
            options.active_clients[0] if options.active_clients else "opencode"
        )
        prefs.sdd_token_budget = sdd_token_budget
        mark_setup_complete(prefs)
        for known_agent in list(prefs.agent_integrations):
            prefs.agent_integrations[known_agent] = known_agent in options.active_clients
        # Workspace-only installs must not write the user-level prefs store ($HOME).
        # The prefs object is still used below to seed the project's opencontext.yaml.
        if not options.workspace_only:
            store.save(prefs)
        # Bridge runtime-affecting prefs into opencontext.yaml — the runtime reads
        # provider/model/security from yaml, not from the prefs store.
        from opencontext_core.config_sync import sync_runtime_prefs_to_yaml

        sync_runtime_prefs_to_yaml(prefs, root=root, overwrite=False)

        # 4. Index project
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.runtime import OpenContextRuntime

            # Anchor project_index.root to the resolved project root before the
            # runtime resolves its storage path. The written opencontext.yaml keeps
            # project_index.root="." (cwd-relative); without this override the
            # onboarding runtime would hash the *current cwd* instead of the project
            # root, so `install <root>` run from a different cwd wrote its state under
            # a different project_id than `index <root>` (which anchors the root via
            # the CLI's _runtime_for_root). That split-state left install's KG/memory
            # in an orphaned hash dir. Resolve the root once here so install and index
            # converge on the same project_id.
            _cfg = load_config_or_defaults(config_path if config_path.exists() else None)
            _cfg = _cfg.model_copy(
                update={"project_index": _cfg.project_index.model_copy(update={"root": str(root)})}
            )
            runtime = OpenContextRuntime(config=_cfg)
            manifest = runtime.index_project(root)
            result.indexed_files = len(manifest.files)
            result.indexed_symbols = len(manifest.symbols)
            kg_stats = manifest.metadata.get("knowledge_graph", {})
            if isinstance(kg_stats, dict):
                result.knowledge_graph_nodes = kg_stats.get("nodes", 0)
                result.knowledge_graph_edges = kg_stats.get("edges", 0)
        except Exception as exc:
            result.warnings.append(f"Auto-index skipped: {exc}")

        # 5. Generate SDD/TDD context
        _sdd_context, sdd_files = write_sdd_context(
            root,
            token_budget_per_phase=sdd_token_budget,
            tdd_mode=options.tdd_mode,
            active_clients=options.active_clients,
            sdd_model_profile=options.sdd_model_profile,
        )
        for f in sdd_files:
            if f.name == "context.json":
                result.sdd_context_path = str(f)

        # 6. Configure agent files through the single Configurator engine.
        # Unlike the old whole-file generator, this MERGES a managed block into
        # existing AGENTS.md/CLAUDE.md (no silent skip when the file exists) and
        # is reversed exactly by `opencontext uninstall`. The project instructions
        # carry the per-client orchestrator profile.
        from opencontext_core.adapters.agent_manifest import (
            _base_rules,
            _orchestrator_section,
        )
        from opencontext_core.configurator import KNOWN_AGENTS, Configurator

        def _instructions(client: str) -> str:
            return _base_rules() + _orchestrator_section(client)

        for client in options.active_clients:
            if client not in KNOWN_AGENTS:
                result.warnings.append(f"Unknown agent target: {client}")
        known_clients = [c for c in options.active_clients if c in KNOWN_AGENTS]
        if known_clients:
            configurator = Configurator(root, instructions_builder=_instructions)
            report = configurator.configure(
                known_clients, scope="local", project_only=options.workspace_only
            )
            for entry in report.get("results", []):
                for path in entry.get("files", []):
                    result.generated_agent_files.append(f"{entry['agent']}: {path}")

        # 7. Generate .opencontext/agents/<client>.md contract files
        agents_dir = resolve_workspace_path(root, StorageMode.local) / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        for client in options.active_clients:
            agent_path = agents_dir / f"{client}.md"
            if agent_path.exists() and not options.force_agent_files:
                result.warnings.append(
                    f"Agent file exists (use --force-agent-files to overwrite): {agent_path}"
                )
                continue
            agent_path.write_text(self._agent_contract_md(client, options), encoding="utf-8")
            result.generated_agent_files.append(str(agent_path))

        # 8. Generate harness.yaml
        harness_path = resolve_workspace_path(root, StorageMode.local) / "harness.yaml"
        self._write_harness_yaml(harness_path, options, sdd_token_budget)
        result.harness_config_path = str(harness_path)

        # 9. Setup MCP if requested
        if options.setup_mcp:
            result.mcp_configured = self._setup_mcp(options, result)

        result.active_clients = list(options.active_clients)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_mcp(self, options: OnboardingOptions, result: OnboardingResult) -> bool:
        """Wire MCP for the active agent clients using the live installer path.

        Reuses :class:`AgentInstaller` — the same path the CLI ``setup`` command
        drives — to write a real ``mcp.json`` entry per agent. This replaces the
        old import of the non-existent ``setup_mcp_for_opencode`` symbol, which
        always raised ``ImportError`` and was swallowed as a warning.
        """
        from opencontext_core.agent_installer import AgentInstaller, AgentTarget

        targets: list[AgentTarget] = []
        for client in options.active_clients:
            try:
                targets.append(AgentTarget(client))
            except ValueError:
                result.warnings.append(f"MCP setup skipped unknown agent target: {client}")
        if not targets:
            return False

        installer = AgentInstaller(project_root=options.root.resolve())
        report = installer.install(targets=targets, location="global", yes=True)
        configured = [r for r in report.get("results", []) if r.get("status") == "configured"]
        return bool(configured)

    @staticmethod
    def _write_gitignore_storage_block(root: Path) -> None:
        """Add a managed .gitignore block so the local index/memory stays out of git.

        Shareable config (opencontext.yaml, AGENTS.md) stays committed; the binary
        graph and memory under .storage/ / .opencontext/ do not. Best-effort.
        """
        try:
            from opencontext_core.configurator.filemerge import (
                inject_managed_lines,
                write_text_atomic,
            )

            path = root / ".gitignore"
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            merged = inject_managed_lines(existing, "storage", [".storage/", ".opencontext/"])
            write_text_atomic(path, merged)
        except Exception:
            return

    def _agent_contract_md(self, client: str, options: OnboardingOptions) -> str:
        """Generate .opencontext/agents/<client>.md contract file."""
        lines = [
            f"# OpenContext Agent Contract: {client}",
            "",
            "## Before acting",
            "1. Read `.opencontext/sdd/context.json`.",
            '2. Build a context pack: `opencontext pack . --query "<task>"'
            " --max-tokens 3000 --mode plan`.",
            "3. Preserve trace_id across all phases.",
            "4. Do not dump the full repository.",
            f"5. Respect TDD mode: `{options.tdd_mode}`.",
            "6. Respect token budget per phase.",
            "7. Write outputs to `.opencontext/runs/<run_id>/artifacts/`.",
            "",
            "## Orchestrator profile",
            f"- Type: `{options.orchestrator_profile}`",
            f"- SDD model profile: `{options.sdd_model_profile}`",
            f"- Active clients: {', '.join(options.active_clients)}",
            "",
            "## Allowed actions",
            "- Read files needed for the current phase",
            "- Use opencontext CLI for context packs, knowledge graph, and memory",
            "- Write to `.opencontext/runs/<run_id>/` for artifacts",
            "",
            "## Forbidden actions",
            "- Do not disable security redaction",
            "- Do not enable external providers without policy approval",
            "- Do not write to `.env`, `secrets/`, `vendor/`",
            "",
            "## Required output",
            "- Every phase must produce a trace_id and artifact",
            "- Archive phase must persist memory and graph deltas",
            "",
        ]
        return "\n".join(lines)

    def _write_harness_yaml(
        self, path: Path, options: OnboardingOptions, token_budget: int
    ) -> None:
        """Generate .opencontext/harness.yaml with phase budgets, gates, and safety rules."""
        import yaml

        harness: dict[str, Any] = {
            "version": "0.1",
            "workflow_defaults": {
                "budget_mode": "warn",
                "artifact_root": ".opencontext/runs",
                "tdd_mode": options.tdd_mode,
            },
            "phases": {
                "explore": {
                    "budget_tokens": token_budget,
                    "gates": [
                        "project_index_exists",
                        "context_pack_created",
                        "no_secret_leakage",
                    ],
                },
                "propose": {
                    "budget_tokens": token_budget,
                    "gates": [
                        "trace_id_created",
                        "included_sources_present",
                        "omissions_recorded",
                    ],
                },
                "apply": {
                    "budget_tokens": token_budget * 2,
                    "gates": [
                        "provider_policy_passed",
                        "approval_required_for_writes",
                    ],
                },
                "verify": {
                    "budget_tokens": token_budget,
                    "gates": ["security_scan_passed", "no_high_risk_exports"],
                },
                "review": {
                    "budget_tokens": token_budget,
                    "gates": ["review_artifact_created"],
                },
                "archive": {
                    "budget_tokens": max(token_budget // 2, 500),
                    # No gates declared: the archive phase persists trace/memory/graph
                    # deltas via its executor, but no dispatch-bound gate evaluates
                    # them — declaring trace_persisted/memory_delta_created/
                    # graph_delta_created here only produced inert, never-evaluated
                    # gates (an honesty gap). Leave empty until real gates exist.
                    "gates": [],
                },
            },
            "agents": {
                "mode": options.orchestrator_profile,
                "active_clients": options.active_clients,
                "default_client": (
                    options.active_clients[0] if options.active_clients else "opencode"
                ),
            },
            "safety": {
                "forbidden_paths": [
                    ".env",
                    "secrets/",
                    "private/",
                    "vendor/",
                    "node_modules/",
                ],
                "forbidden_commands": ["rm -rf", "git push --force", "curl | bash"],
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(harness, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )


def is_first_run(root: str | Path) -> bool:
    """Detect whether this project has been set up yet.

    Checks both opencontext.yaml existence and the setup_completed flag
    in user preferences. Returns True if the project needs onboarding.
    """
    root_path = Path(root)
    config_path = root_path / "opencontext.yaml"
    workspace_marker = resolve_workspace_path(root_path, StorageMode.local) / "sdd" / "context.json"

    # Neither config nor workspace marker → first run
    if not config_path.exists() and not workspace_marker.exists():
        return True

    # Check if setup was completed in user prefs
    try:
        from opencontext_core.user_prefs import UserConfigStore

        store = UserConfigStore()
        prefs = store.load()
        return not prefs.setup_completed
    except Exception:
        # If we can't read user prefs, presence of either file is good enough
        return False
