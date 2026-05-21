"""Knowledge graph CLI commands."""

from __future__ import annotations

import json
from typing import Any

from opencontext_core.dx.console_styles import console
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


def add_kg_parser(subparsers: Any) -> None:
    """Add knowledge-graph command parsers."""
    kg_parser = subparsers.add_parser("knowledge-graph", help="Query the code knowledge graph.")
    kg_sub = kg_parser.add_subparsers(dest="kg_command", required=True)

    kg_search = kg_sub.add_parser("search", help="Search for symbols.")
    kg_search.add_argument("query", help="Search query.")
    kg_search.add_argument("--limit", type=int, default=20)
    kg_search.add_argument("--json", action="store_true")

    kg_query = kg_sub.add_parser("query", help="Query graph by kind.")
    kg_query.add_argument("query", help="Query string.")
    kg_query.add_argument("--kind", choices=["function", "class", "module", "variable"])
    kg_query.add_argument("--limit", type=int, default=20)
    kg_query.add_argument("--json", action="store_true")

    kg_context = kg_sub.add_parser("context", help="Build context for a task.")
    kg_context.add_argument("task", help="Task description.")
    kg_context.add_argument("--max-nodes", type=int, default=20)
    kg_context.add_argument("--json", action="store_true")

    kg_callers = kg_sub.add_parser("callers", help="Find callers of a symbol.")
    kg_callers.add_argument("symbol", help="Symbol name.")
    kg_callers.add_argument("--depth", type=int, default=2)
    kg_callers.add_argument("--json", action="store_true")

    kg_callees = kg_sub.add_parser("callees", help="Find callees of a symbol.")
    kg_callees.add_argument("symbol", help="Symbol name.")
    kg_callees.add_argument("--depth", type=int, default=2)
    kg_callees.add_argument("--json", action="store_true")

    kg_impact = kg_sub.add_parser("impact", help="Analyze change impact.")
    kg_impact.add_argument("symbol", help="Symbol name.")
    kg_impact.add_argument("--radius", type=int, default=2)
    kg_impact.add_argument("--json", action="store_true")

    kg_sub.add_parser("status", help="Check index status.")


def handle_kg(args: Any) -> None:
    """Handle knowledge-graph commands."""
    command = args.kg_command
    query = getattr(args, "query", "")
    symbol = getattr(args, "symbol", "")
    task = getattr(args, "task", "")
    limit = getattr(args, "limit", 20)
    depth = getattr(args, "depth", 2)
    radius = getattr(args, "radius", 2)
    getattr(args, "max_nodes", 20)
    json_output = getattr(args, "json", False)
    getattr(args, "root", ".")

    kg = KnowledgeGraph()

    if command == "search":
        results = kg.search(query, limit=limit)
        if json_output:
            print(json.dumps(results, indent=2))
        else:
            console.header(f"Search: {query}")
            if not results:
                console.dim("No results found.")
            else:
                for r in results:
                    console.print(f"  [bold]{r.get('name', '?')}[/] ({r.get('kind', '?')})")
                    console.print(f"    [dim]{r.get('file_path', '?')}:{r.get('line', '?')}[/]")

    elif command == "query":
        results = kg.search(query, limit=limit)
        if json_output:
            print(json.dumps(results, indent=2))
        else:
            console.header(f"Query: {query}")
            for r in results:
                console.print(f"  [bold]{r.get('name', '?')}[/]")

    elif command == "context":
        console.header(f"Context: {task}")
        console.info("Context building uses the indexed knowledge graph.")
        console.info("Run 'opencontext pack' for full context generation.")

    elif command == "callers":
        console.header(f"Callers: {symbol}")
        results = _find_callers(kg, symbol, depth)
        if json_output:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                console.info("No callers found.")
            else:
                for r in results:
                    console.print(
                        f"  [bold]{r['name']}[/] ({r['kind']}) "
                        f"- [dim]{r['file_path']}:{r['line']}[/] "
                        f"(depth {r['depth']})"
                    )

    elif command == "callees":
        console.header(f"Callees: {symbol}")
        results = _find_callees(kg, symbol, depth)
        if json_output:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                console.info("No callees found.")
            else:
                for r in results:
                    console.print(
                        f"  [bold]{r['name']}[/] ({r['kind']}) "
                        f"- [dim]{r['file_path']}:{r['line']}[/] "
                        f"(depth {r['depth']})"
                    )

    elif command == "impact":
        console.header(f"Impact: {symbol}")
        results = _find_callers(kg, symbol, radius)
        if json_output:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                console.info("No impact found.")
            else:
                for r in results:
                    console.print(
                        f"  [bold]{r['name']}[/] ({r['kind']}) "
                        f"- [dim]{r['file_path']}:{r['line']}[/] "
                        f"(depth {r['depth']})"
                    )

    elif command == "status":
        stats = kg.get_stats()
        if json_output:
            print(json.dumps(stats, indent=2))
        else:
            console.header("Knowledge Graph Status")
            console.table(
                "Statistics",
                ["Metric", "Count"],
                [
                    ["Nodes", str(stats.get("nodes", 0))],
                    ["Edges", str(stats.get("edges", 0))],
                    ["Files", str(stats.get("files", 0))],
                ],
            )
    else:
        console.error(f"Unknown knowledge-graph command: {command}")

    kg.close()


def _find_callers(kg: KnowledgeGraph, symbol: str, depth: int) -> list[dict[str, Any]]:
    """Find callers of a symbol using the call graph."""

    from opencontext_core.indexing.call_graph import CallGraphAnalyzer

    analyzer = CallGraphAnalyzer(kg.db)
    conn = kg.db._connect()
    rows = conn.execute(
        "SELECT id FROM nodes WHERE name = ? ORDER BY line LIMIT 1", (symbol,)
    ).fetchall()
    if not rows:
        return []

    node_id = rows[0]["id"]
    return analyzer.get_callers(node_id, depth)


def _find_callees(kg: KnowledgeGraph, symbol: str, depth: int) -> list[dict[str, Any]]:
    """Find callees of a symbol using the call graph."""

    from opencontext_core.indexing.call_graph import CallGraphAnalyzer

    analyzer = CallGraphAnalyzer(kg.db)
    conn = kg.db._connect()
    rows = conn.execute(
        "SELECT id FROM nodes WHERE name = ? ORDER BY line LIMIT 1", (symbol,)
    ).fetchall()
    if not rows:
        return []

    node_id = rows[0]["id"]
    return analyzer.get_callees(node_id, depth)
