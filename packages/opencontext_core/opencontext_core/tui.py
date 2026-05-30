"""Interactive TUI for OpenContext.

Provides a terminal UI for:
- Project setup and initialization
- Knowledge graph indexing and queries
- SDD workflow management
- Privacy rules management
- Health checks and diagnostics

The TUI is the primary interface for users who prefer a guided experience
over command-line flags.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

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

    # ── Main loop ─────────────────────────────────────────────────────────────

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
                values=self.MENU_VALUES,
            ).run()
        return self._fallback_menu()

    def _fallback_menu(self) -> str | None:
        """Simple text-based menu when prompt_toolkit is not available."""
        print("\nOpenContext Menu:")
        for key, label in self.FALLBACK_MAPPING.items():
            print(f"  {key}. {label}")
        choice = input("\nSelect: ").strip()
        return self.FALLBACK_MAPPING.get(choice)

    def _handle_choice(self, choice: str) -> None:
        """Handle menu selection."""
        handlers: dict[str, Callable[[], None]] = {
            "init": self._do_init,
            "index": self._do_index,
            "search": self._do_search,
            "context": self._do_context,
            "impact": self._do_impact,
            "sdd": self._do_sdd,
            "harness": self._do_harness_apply,
            "report": self._do_report,
            "privacy": self._do_privacy,
            "doctor": self._do_doctor,
            "status": self._do_status,
        }
        handler = handlers.get(choice)
        if handler:
            try:
                handler()
            except Exception as exc:
                print(f"\nError: {exc}")
                input("\nPress Enter to continue...")
        input("\nPress Enter to continue...")

    # ── Menu definition ─────────────────────────────────────────────────────────

    MENU_VALUES: ClassVar[list[tuple[str, str]]] = [
        ("init", "Initialize project"),
        ("index", "Index project into knowledge graph"),
        ("search", "Search knowledge graph"),
        ("context", "Build context for a task"),
        ("impact", "Analyze change impact"),
        ("sdd", "Run SDD workflow"),
        ("harness", "Run harness (apply-only)"),
        ("report", "View harness report"),
        ("privacy", "Manage privacy rules"),
        ("doctor", "Run health checks"),
        ("status", "Show project status"),
        ("quit", "Exit"),
    ]

    FALLBACK_MAPPING: ClassVar[dict[str, str]] = {
        "1": "init",
        "2": "index",
        "3": "search",
        "4": "context",
        "5": "impact",
        "6": "sdd",
        "7": "harness",
        "8": "report",
        "9": "privacy",
        "a": "doctor",
        "b": "status",
        "0": "quit",
    }

    # ── Actions ────────────────────────────────────────────────────────────────

    def _do_init(self) -> None:
        """Initialize the project workspace."""
        print("\n--- Initialize Project ---")
        if self.config_path.exists():
            print(f"Config already exists: {self.config_path}")
            return

        from opencontext_core.config import default_config_data
        from opencontext_core.workspace.layout import ensure_workspace

        ensure_workspace(self.project_root)
        import yaml

        config_data = default_config_data()
        self.config_path.write_text(
            yaml.safe_dump(config_data, sort_keys=False),
            encoding="utf-8",
        )
        print(f"Created: {self.config_path}")
        print("Project initialized. Run 'opencontext onboard' for full setup.")

    def _do_index(self) -> None:
        """Index the project into the knowledge graph."""
        print("\n--- Index Project ---")
        try:
            from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

            kg = KnowledgeGraph()
            print(f"Indexing {self.project_root}... (this may take a moment)")
            stats = kg.index_project(self.project_root)
            kg.close()
            print(
                f"\nIndexed: {stats.get('files_indexed', 0)} files, "
                f"{stats.get('nodes', 0)} nodes, "
                f"{stats.get('edges', 0)} edges"
            )
        except Exception as exc:
            print(f"Indexing failed: {exc}")

    def _do_search(self) -> None:
        """Search the knowledge graph."""
        print("\n--- Search Knowledge Graph ---")
        query = input("Search query: ").strip()
        if not query:
            return
        try:
            from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

            kg = KnowledgeGraph()
            results = kg.search(query, limit=20)
            kg.close()
            if not results:
                print("No results found.")
            else:
                print(f"\n{len(results)} results:")
                for r in results:
                    print(
                        f"  {r.get('name', '?')} ({r.get('kind', '?')}) "
                        f"@ {r.get('file_path', '?')}:{r.get('line', '?')}"
                    )
        except Exception as exc:
            print(f"Search failed: {exc}")

    def _do_context(self) -> None:
        """Build context for a task."""
        print("\n--- Build Context ---")
        task = input("Task description: ").strip()
        if not task:
            return
        try:
            from opencontext_core.indexing.context_builder import ContextBuilder

            builder = ContextBuilder()
            context = builder.build_context(task=task, max_nodes=20, root=self.project_root)
            rendered = builder.render(context)
            builder.close()
            print(f"\n--- Context (estimated {context.total_tokens_estimate} tokens) ---")
            print(rendered[:3000])
            if len(rendered) > 3000:
                print(f"\n... (truncated, full context has {len(rendered)} chars)")
        except Exception as exc:
            print(f"Context build failed: {exc}")

    def _do_impact(self) -> None:
        """Analyze change impact."""
        print("\n--- Analyze Impact ---")
        symbol = input("Symbol name: ").strip()
        if not symbol:
            return
        try:
            from opencontext_core.indexing.graph_db import GraphDatabase
            from opencontext_core.indexing.impact_analysis import ImpactAnalyzer

            db = GraphDatabase()
            impact = ImpactAnalyzer(db)
            results = db.search_fts(symbol, limit=10)
            node_id = next(
                (r.get("id") for r in results if r.get("name") == symbol),
                None,
            )
            if node_id is None:
                print(f"Symbol not found: {symbol}")
                db.close()
                return
            result = impact.analyze(node_id, depth=2)
            print(f"\nImpact for {symbol}:")
            print(f"  Affected files: {len(result.affected_files)}")
            for f in sorted(result.affected_files)[:10]:
                print(f"    {f}")
            if len(result.affected_files) > 10:
                print(f"    ... and {len(result.affected_files) - 10} more")
            db.close()
        except Exception as exc:
            print(f"Impact analysis failed: {exc}")

    def _do_sdd(self) -> None:
        """Run the full SDD workflow."""
        print("\n--- SDD Workflow ---")
        task = input("What do you want to build/change? ").strip()
        if not task:
            return
        print("\nRunning SDD workflow...")
        print("Phases: explore -> propose -> spec -> design -> tasks")
        print("        -> apply -> verify -> review -> archive")
        try:
            from opencontext_core.harness.models import BudgetMode
            from opencontext_core.harness.runner import HarnessRunner

            runner = HarnessRunner(root=self.project_root)
            result = runner.run(
                workflow="sdd",
                task=task,
                budget_mode=BudgetMode.WARN,
            )
            status = result.status.value if hasattr(result.status, "value") else str(result.status)
            print(f"\nRun complete: {status}")
            print(f"Run ID: {result.run_id}")
            print(f"  Phases: {len(result.ledgers)}")
            print(f"  Gates: {len(result.gates)} passed / {len(result.gates)} total")
            if result.warnings:
                print(f"  Warnings: {len(result.warnings)}")
                for w in result.warnings[:3]:
                    print(f"    ⚠ {w}")
        except Exception as exc:
            print(f"SDD run failed: {exc}")

    def _do_harness_apply(self) -> None:
        """Run harness in apply-only mode."""
        print("\n--- Harness: Apply Only ---")
        task = input("Task name (must match a prior explore run): ").strip()
        if not task:
            return
        try:
            from opencontext_core.harness.models import BudgetMode
            from opencontext_core.harness.runner import HarnessRunner

            runner = HarnessRunner(root=self.project_root)
            result = runner.run(workflow="apply-only", task=task, budget_mode=BudgetMode.WARN)
            status = result.status.value if hasattr(result.status, "value") else str(result.status)
            print(f"\nRun complete: {status}")
            print(f"Run ID: {result.run_id}")
        except Exception as exc:
            print(f"Harness run failed: {exc}")

    def _do_report(self) -> None:
        """View a past harness run report."""
        import json

        print("\n--- Harness Reports ---")
        runs_dir = self.project_root / ".opencontext" / "runs"
        if not runs_dir.exists():
            print("No runs found. Run 'opencontext harness run' first.")
            return

        runs = sorted(
            (d for d in runs_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if not runs:
            print("No runs found.")
            return

        print("Recent runs (newest first):")
        for i, r in enumerate(runs[:10]):
            report = r / "archive-report.json"
            status = "?"
            if report.exists():
                data = json.loads(report.read_text(encoding="utf-8"))
                status = data.get("status", "?")
            print(f"  [{i + 1}] {r.name} — {status}")

        sel = input("\nEnter run number to view (or Enter to cancel): ").strip()
        if not sel:
            return
        try:
            idx = int(sel) - 1
            target = runs[idx]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return

        report = target / "archive-report.json"
        if report.exists():
            data = json.loads(report.read_text(encoding="utf-8"))
            print(f"\n{'=' * 50}")
            print(f"  Run: {target.name}")
            print(f"{'=' * 50}")
            print(f"  Task: {data.get('task', '?')}")
            print(f"  Status: {data.get('status', '?')}")
            print(f"  Summary: {data.get('summary', '?')}")
            gates = data.get("gates", {})
            print(
                f"  Gates: passed={gates.get('passed', 0)}, "
                f"warning={gates.get('warning', 0)}, "
                f"failed={gates.get('failed', 0)}"
            )
        else:
            print(f"No archive-report.json found in {target}")

    def _do_privacy(self) -> None:
        """Manage privacy rules."""
        print("\n--- Privacy Rules ---")
        privacy_path = self.project_root / ".opencontext" / "privacy.yaml"
        if not privacy_path.exists():
            print("No privacy rules configured.")
            if not self._yes_no(
                title="Create a privacy rule?",
                text="Create privacy rules?",
                default=False,
            ):
                return
            print("(Use CLI: opencontext privacy add --name ... --scope ...)")
            return

        import yaml

        data = yaml.safe_load(privacy_path.read_text(encoding="utf-8")) or {}
        rules = data.get("privacy_rules", [])
        if not rules:
            print("No privacy rules configured.")
            return
        print(f"{len(rules)} rule(s):")
        for r in rules:
            scopes = ", ".join(r.get("permission_scopes", []))
            print(f"  • {r.get('name', r.get('id', '?'))}")
            print(f"    Scopes: {scopes}")
            print(f"    Classification: {r.get('data_classification', '?')}")

    def _do_doctor(self) -> None:
        """Run health checks."""
        print("\n--- Health Checks ---")
        try:
            from opencontext_core.config import load_config
            from opencontext_core.doctor.checks import run_doctor

            config_path = str(self.config_path) if self.config_path.exists() else None
            config = load_config(config_path)  # type: ignore[arg-type]
            checks = run_doctor(config)
            for check in checks:
                icon = "PASS" if check.ok else "FAIL"
                print(f"  [{icon}] {check.name}: {check.details}")
        except Exception as exc:
            print(f"Health check error: {exc}")

    def _do_status(self) -> None:
        """Show project status."""
        print("\n--- Project Status ---")
        print(f"Root: {self.project_root}")

        # Config
        config_status = "exists" if self.config_path.exists() else "missing"
        print(f"Config: {config_status}")

        # Workspace
        workspace_ok = self.opencontext_dir.exists()
        print(f"Workspace: {'ok' if workspace_ok else 'missing'}")

        # Knowledge graph
        db_path = self.opencontext_dir / "storage" / "opencontext" / "codegraph.db"
        if db_path.exists():
            try:
                from opencontext_core.indexing.graph_db import GraphDatabase

                db = GraphDatabase(db_path=db_path)
                stats = db.get_stats()
                db.close()
                nodes = stats.get("nodes", 0)
                edges = stats.get("edges", 0)
                print(f"Knowledge graph: {nodes} nodes, {edges} edges")
            except Exception:
                print("Knowledge graph: error reading")
        else:
            print("Knowledge graph: not indexed (run 'opencontext index')")

        # Privacy rules
        privacy_path = self.opencontext_dir / "privacy.yaml"
        if privacy_path.exists():
            import yaml

            data = yaml.safe_load(privacy_path.read_text(encoding="utf-8")) or {}
            rules = data.get("privacy_rules", [])
            profile = data.get("privacy_profile", "off")
            print(f"Privacy rules: {len(rules)} rule(s) — profile: {profile}")
        else:
            print("Privacy rules: none configured")

        # Recent runs
        runs_dir = self.opencontext_dir / "runs"
        if runs_dir.exists():
            runs = sorted(
                (d for d in runs_dir.iterdir() if d.is_dir()),
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if runs:
                latest = runs[0]
                print(f"Last run: {latest.name}")
                report = latest / "archive-report.json"
                if report.exists():
                    import json

                    rd = json.loads(report.read_text(encoding="utf-8"))
                    print(f"  Status: {rd.get('status', '?')}")

    def _fallback_mode(self) -> None:
        """Fallback mode without prompt_toolkit."""
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║            OpenContext — Simple Text Mode                   ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print("Install prompt_toolkit for the full TUI: pip install prompt_toolkit")
        self._tui_mode()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _yes_no(self, title: str, text: str, default: bool = False) -> bool:
        """Ask a yes/no question."""
        if PROMPT_TOOLKIT_AVAILABLE:
            return bool(yes_no_dialog(title=title, text=text).run())
        answer = input(f"{title} (y/N): ").strip().lower()
        return answer in ("y", "yes")
