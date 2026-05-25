"""Interactive TUI for OpenContext.

Provides a terminal UI for:
- Project setup and indexing
- Knowledge graph queries
- SDD workflow management
- Agent configuration
- Memory browsing
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

try:
    from prompt_toolkit.shortcuts import radiolist_dialog, yes_no_dialog

    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


class OpenContextTUI:
    """Interactive TUI for OpenContext operations.

    Provides a menu-driven interface for common operations
    when prompt_toolkit is available. Falls back to simple
    text prompts otherwise.
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.opencontext_dir = self.project_root / ".opencontext"
        self.config_path = self.project_root / "opencontext.yaml"

    def run(self) -> None:
        """Run the interactive TUI main loop."""

        if not PROMPT_TOOLKIT_AVAILABLE:
            self._fallback_mode()
            return

        self._tui_mode()

    def _tui_mode(self) -> None:
        """Run full TUI with prompt_toolkit."""

        print("╔══════════════════════════════════════════════════════════════╗")
        print("║               OpenContext Interactive TUI                    ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()

        while True:
            choice = self._show_main_menu()
            if choice is None or choice == "quit":
                break
            self._handle_choice(choice)

    def _show_main_menu(self) -> str | None:
        """Show main menu and return selection."""

        if PROMPT_TOOLKIT_AVAILABLE:
            return radiolist_dialog(
                title="OpenContext Menu",
                text="Select an operation:",
                values=[
                    ("init", "Initialize project"),
                    ("index", "Index project into knowledge graph"),
                    ("search", "Search knowledge graph"),
                    ("context", "Build context for task"),
                    ("impact", "Analyze change impact"),
                    ("install", "Install agent configurations"),
                    ("sdd", "Run SDD workflow"),
                    ("doctor", "Run health checks"),
                    ("status", "Show project status"),
                    ("quit", "Exit"),
                ],
            ).run()
        else:
            print("\nOpenContext Menu:")
            print("  1. Initialize project")
            print("  2. Index project")
            print("  3. Search knowledge graph")
            print("  4. Build context")
            print("  5. Analyze impact")
            print("  6. Install agents")
            print("  7. Run SDD workflow")
            print("  8. Run health checks")
            print("  9. Show status")
            print("  0. Exit")
            choice = input("\nSelect: ").strip()
            mapping = {
                "1": "init",
                "2": "index",
                "3": "search",
                "4": "context",
                "5": "impact",
                "6": "install",
                "7": "sdd",
                "8": "doctor",
                "9": "status",
                "0": "quit",
            }
            return mapping.get(choice)

    def _handle_choice(self, choice: str) -> None:
        """Handle menu selection."""

        handlers: dict[str, Callable[[], None]] = {
            "init": self._do_init,
            "index": self._do_index,
            "search": self._do_search,
            "context": self._do_context,
            "impact": self._do_impact,
            "install": self._do_install,
            "sdd": self._do_sdd,
            "doctor": self._do_doctor,
            "status": self._do_status,
        }

        handler = handlers.get(choice)
        if handler:
            try:
                handler()
            except Exception as exc:
                print(f"\nError: {exc}")
                input("Press Enter to continue...")

    def _do_init(self) -> None:
        """Initialize project."""

        print("\n--- Initialize Project ---")
        if self.config_path.exists():
            if PROMPT_TOOLKIT_AVAILABLE:
                overwrite = yes_no_dialog(
                    title="Config exists",
                    text=f"{self.config_path} already exists. Overwrite?",
                ).run()
            else:
                overwrite = input("Config exists. Overwrite? (y/N): ").lower() == "y"
            if not overwrite:
                return

        from opencontext_core.workspace.layout import ensure_workspace

        created = ensure_workspace(self.project_root)
        print("Workspace created:")
        for path in created:
            print(f"  {path}")

        if not self.config_path.exists():
            import yaml

            from opencontext_core.config import default_config_data

            config_data = default_config_data()
            self.config_path.write_text(
                yaml.safe_dump(config_data, sort_keys=False),
                encoding="utf-8",
            )
            print(f"Config written: {self.config_path}")

    def _do_index(self) -> None:
        """Index project into knowledge graph."""

        print("\n--- Index Project ---")
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()
        print(f"Indexing {self.project_root}...")
        stats = kg.index_project(self.project_root)
        kg.close()

        print("\nIndexed:")
        print(f"  Files: {stats['files_indexed']}")
        print(f"  Nodes: {stats['nodes']}")
        print(f"  Edges: {stats['edges']}")

    def _do_search(self) -> None:
        """Search knowledge graph."""

        print("\n--- Search Knowledge Graph ---")
        query = input("Search query: ").strip()
        if not query:
            return

        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()
        results = kg.search(query, limit=20)
        kg.close()

        print(f"\nFound {len(results)} results:")
        for r in results:
            print(f"  {r.get('name')} ({r.get('kind')}) @ {r.get('file_path')}:{r.get('line')}")

    def _do_context(self) -> None:
        """Build context for task."""

        print("\n--- Build Context ---")
        task = input("Task description: ").strip()
        if not task:
            return

        from opencontext_core.indexing.context_builder import ContextBuilder

        builder = ContextBuilder()
        context = builder.build_context(task=task, max_nodes=20, root=self.project_root)
        rendered = builder.render(context)
        builder.close()

        print(f"\n{rendered[:2000]}...")
        print(f"\nEstimated tokens: {context.total_tokens_estimate}")

    def _do_impact(self) -> None:
        """Analyze change impact."""

        print("\n--- Analyze Impact ---")
        symbol = input("Symbol name: ").strip()
        if not symbol:
            return

        from opencontext_core.indexing.graph_db import GraphDatabase

        db = GraphDatabase()
        from opencontext_core.indexing.impact_analysis import ImpactAnalyzer

        impact = ImpactAnalyzer(db)
        results = db.search_fts(symbol, limit=10)
        node_id = None
        for r in results:
            if r.get("name") == symbol:
                node_id = r.get("id")
                break

        if node_id is None:
            print(f"Symbol not found: {symbol}")
            db.close()
            return

        result = impact.analyze(node_id, depth=2)

        print(f"\nImpact analysis for {symbol}:")
        print("  Risk level: N/A")
        print(f"  Affected files: {len(result.affected_files)}")
        for f in sorted(result.affected_files)[:10]:
            print(f"    {f}")
        if len(result.affected_files) > 10:
            print(f"    ... and {len(result.affected_files) - 10} more")

    def _do_install(self) -> None:
        """Install agent configurations."""

        print("\n--- Install Agent Configurations ---")
        from opencontext_core.agent_installer import AgentInstaller

        installer = AgentInstaller(project_root=self.project_root)
        detected = installer.detect_installed_agents()

        if detected:
            print(f"Detected agents: {', '.join(a.value for a in detected)}")
            if PROMPT_TOOLKIT_AVAILABLE:
                install = yes_no_dialog(
                    title="Install",
                    text="Install OpenContext integration for detected agents?",
                ).run()
            else:
                install = input("Install? (Y/n): ").lower() != "n"

            if install:
                result = installer.install(targets=detected, location="global")
                print(f"\nInstalled for {result['agents_configured']} agents")
        else:
            print("No agents detected. Install agents manually first.")

    def _do_sdd(self) -> None:
        """Run SDD workflow."""

        print("\n--- SDD Workflow ---")
        query = input("What do you want to build/change? ").strip()
        if not query:
            return

        print(f"\nRunning SDD flow for: {query}")
        print("Phases: explore -> propose -> spec -> design -> tasks -> apply -> verify -> archive")
        print("(Scaffold mode - requires sub-agent support)")

    def _do_doctor(self) -> None:
        """Run health checks."""

        print("\n--- Health Checks ---")
        from opencontext_core.config import load_config
        from opencontext_core.doctor.checks import run_doctor

        try:
            config_path: str | None = str(self.config_path) if self.config_path.exists() else None
            config = load_config(config_path)  # type: ignore[arg-type]
            checks = run_doctor(config)
            for check in checks:
                status = "PASS" if check.ok else "FAIL"
                print(f"  [{status}] {check.name}: {check.details}")
        except Exception as exc:
            print(f"  Error: {exc}")

    def _do_status(self) -> None:
        """Show project status."""

        print("\n--- Project Status ---")
        print(f"Root: {self.project_root}")
        config_status = "exists" if self.config_path.exists() else "missing"
        print(f"Config: {self.config_path} ({config_status})")
        workspace_status = "exists" if self.opencontext_dir.exists() else "missing"
        print(f"Workspace: {self.opencontext_dir} ({workspace_status})")

        # Knowledge graph stats
        db_path = self.opencontext_dir / "storage" / "opencontext" / "codegraph.db"
        if db_path.exists():
            from opencontext_core.indexing.graph_db import GraphDatabase

            db = GraphDatabase(db_path=db_path)
            stats = db.get_stats()
            db.close()
            print(f"Knowledge graph: {stats.get('nodes', 0)} nodes, {stats.get('edges', 0)} edges")
        else:
            print("Knowledge graph: not indexed")

    def _fallback_mode(self) -> None:
        """Fallback mode without prompt_toolkit."""

        print("Interactive TUI requires prompt_toolkit.")
        print("Install with: pip install prompt_toolkit")
        print()
        print("Falling back to simple menu...")
        self._tui_mode()
