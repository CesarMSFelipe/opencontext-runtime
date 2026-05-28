"""Knowledge graph CLI commands."""

from __future__ import annotations

import json
import os
import sqlite3
import webbrowser
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

    kg_trace = kg_sub.add_parser("trace", help="Trace path between two symbols.")
    kg_trace.add_argument("source", help="Source symbol name.")
    kg_trace.add_argument("target", help="Target symbol name.")
    kg_trace.add_argument("--max-depth", type=int, default=10, help="Max BFS depth.")
    kg_trace.add_argument("--json", action="store_true")

    kg_view = kg_sub.add_parser(
        "view",
        help="Visualize project structure from the knowledge graph.",
        description=(
            "Shows project architecture in multiple formats.\n\n"
            "  opencontext knowledge-graph view               Mermaid graph (default)\n"
            "  opencontext knowledge-graph view --format tree  Directory tree\n"
            "  opencontext knowledge-graph view --format ascii ASCII art tree\n"
            "  opencontext knowledge-graph view --output graph.md   Save to file\n"
        ),
    )
    kg_view.add_argument(
        "--max-nodes", type=int, default=50, help="Max nodes in Mermaid graph."
    )
    kg_view.add_argument(
        "--tree",
        action="store_true",
        help="[DEPRECATED: use --format tree] Show directory tree instead of Mermaid.",
    )
    kg_view.add_argument(
        "--format",
        choices=["mermaid", "tree", "ascii", "text"],
        default=None,
        help="Output format (default: mermaid unless --tree is set).",
    )
    kg_view.add_argument(
        "--output", default=None, help="Save output to file (default: print to stdout)."
    )


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
                _print_graph_results(results)

    elif command == "callees":
        console.header(f"Callees: {symbol}")
        results = _find_callees(kg, symbol, depth)
        if json_output:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                console.info("No callees found.")
            else:
                _print_graph_results(results)

    elif command == "impact":
        console.header(f"Impact: {symbol}")
        results = _find_callers(kg, symbol, radius)
        if json_output:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                console.info("No impact found.")
            else:
                _print_graph_results(results, show_depth_label=True)

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
    elif command == "trace":
        console.header(f"Trace: {symbol} -> ...")
        source_name = getattr(args, "source", "")
        target_name = getattr(args, "target", "")
        max_depth = getattr(args, "max_depth", 10)
        json_output = getattr(args, "json", False)

        from opencontext_core.indexing.call_graph import CallGraphAnalyzer

        analyzer = CallGraphAnalyzer(kg.db)
        source_id = _find_node_id(kg, source_name)
        target_id = _find_node_id(kg, target_name)

        if source_id is None:
            console.error(f"Symbol not found: {source_name}")
            return
        if target_id is None:
            console.error(f"Symbol not found: {target_name}")
            return

        result = analyzer.find_path(source_id, target_id, max_depth=max_depth)

        if json_output:
            import json as _json
            print(_json.dumps({
                "found": result.found,
                "path": result.path,
                "depth_exceeded": result.depth_exceeded,
                "hops": result.hops,
            }, indent=2))
        elif result.found:
            console.print(f"[green]Found path[/] ([bold]{result.hops}[/] hop{'s' if result.hops != 1 else ''})")
            for i, node in enumerate(result.path):
                console.print(f"  {i + 1}. [bold]{node['name']}[/] ({node['file_path']}:{node['line']})")
        else:
            msg = "Maximum depth reached." if result.depth_exceeded else "No path exists."
            console.print(f"[yellow]{msg}[/]")

    elif command == "view":
        max_nodes = getattr(args, "max_nodes", 50)
        output_path = getattr(args, "output", None)
        use_tree = getattr(args, "tree", False)
        fmt = getattr(args, "format", None)

        # Resolve format: --tree is a shorthand for --format tree
        if fmt is None:
            fmt = "tree" if use_tree else "mermaid"

        if fmt in ("tree", "ascii", "text"):
            label = f"Directory tree ({fmt})"
            if fmt == "ascii":
                output = _generate_ascii_tree(kg)
            else:
                output = _generate_tree_text(kg)

            if output_path:
                with open(output_path, "w") as f:
                    f.write(output)
                console.print(f"  ✓ {label} saved to [cyan]{output_path}[/]")
            elif fmt == "ascii":
                # Plain ASCII, no rich formatting
                print(output)
            else:
                _display_rich_tree(kg)
        else:
            label = "Mermaid graph"
            output = _generate_mermaid_graph(kg, max_nodes)
            if output_path:
                with open(output_path, "w") as f:
                    f.write(output)
                console.print(f"  ✓ {label} saved to [cyan]{output_path}[/]")
            else:
                # Show Mermaid code and auto-generate an HTML viewer
                console.print(output)

                # Extract just the mermaid diagram code (without markdown fences or summary)
                mermaid_code = output
                if mermaid_code.startswith("```mermaid"):
                    mermaid_code = mermaid_code.split("```mermaid", 1)[1]
                closing = mermaid_code.find("\n```")
                if closing >= 0:
                    mermaid_code = mermaid_code[:closing]
                mermaid_code = mermaid_code.strip()

                html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knowledge Graph — Project Structure</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  body {{ background: #fff; color: #333; font-family: sans-serif; padding: 2rem; }}
  .mermaid {{ max-width: 100%; }}
  .info {{ margin-top: 1rem; color: #666; font-size: 0.9em; }}
</style>
</head>
<body>
<div class="mermaid">
{mermaid_code}
</div>
<div class="info">Auto-generated from OpenContext knowledge graph</div>
<script>mermaid.initialize({{ startOnLoad: true }});</script>
</body>
</html>"""
                html_path = os.path.join(os.getcwd(), "opencontext-kg-view.html")
                with open(html_path, "w") as f:
                    f.write(html)
                console.print()
                console.print(f"  HTML viewer saved as [cyan]{html_path}[/]")
                webbrowser.open(f"file://{html_path}")
    else:
        console.error(f"Unknown knowledge-graph command: {command}")

    kg.close()


def _find_node_id(kg: KnowledgeGraph, symbol: str) -> int | None:
    """Find a node ID by symbol name."""
    conn = kg.db._connect()
    rows = conn.execute(
        "SELECT id FROM nodes WHERE name = ? ORDER BY line LIMIT 1", (symbol,)
    ).fetchall()
    return rows[0]["id"] if rows else None


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


def _generate_mermaid_graph(kg: KnowledgeGraph, max_nodes: int = 50) -> str:
    """Generate a Mermaid graph showing the project's structure.

    Groups nodes by module directory and shows key classes with
    cross-module call relationships. Experimental — gives a quick
    architectural overview after indexing.
    """
    import collections

    conn = kg.db._connect()

    # Get all top-level classes and functions
    rows = conn.execute("""
        SELECT n.name, n.kind, n.file_path
        FROM nodes n
        WHERE n.kind IN ('class', 'function')
          AND (n.container IS NULL OR n.container = '')
        ORDER BY n.file_path, n.kind, n.name
    """).fetchall()

    # Build a group key that reflects the module structure
    def _module_key(path: str) -> str:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "packages":
            # packages/opencontext_core/opencontext_core/...
            return f"{parts[0]}/{parts[1]}"
        # tests/, docs/, examples/, or root files
        return parts[0]

    dir_groups: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for name, kind, file_path in rows:
        dir_groups[_module_key(file_path)].append({
            "name": name,
            "kind": kind,
            "file": file_path,
        })

    total_nodes = sum(len(nodes) for nodes in dir_groups.values())

    # Pick groups — spread max_nodes evenly so smaller modules get visibility
    sorted_groups = sorted(dir_groups.items(), key=lambda x: -len(x[1]))
    num_groups = min(len(sorted_groups), max(5, max_nodes // 5))
    # Give each group a fair share: at least 2 per group, leftovers to biggest
    per_group = max(2, max_nodes // num_groups)
    included_groups: list[tuple[str, list[dict[str, str]]]] = []
    included_count = 0
    for i, (group_key, nodes) in enumerate(sorted_groups):
        if i >= num_groups:
            break
        # Smaller groups get fewer slots
        share = min(per_group, len(nodes))
        if included_count + share > max_nodes:
            share = max_nodes - included_count
        if share <= 0:
            break
        included_groups.append((group_key, nodes[:share]))
        included_count += share

    node_id_map: dict[str, str] = {}
    node_counter = 0

    lines: list[str] = []
    lines.append("```mermaid")
    lines.append("flowchart TD")
    lines.append("  %% Project structure — auto-generated from knowledge graph")
    lines.append(f"  %% {included_count} symbols from {len(included_groups)} modules (max {max_nodes})")

    for group_key, nodes in included_groups:
        sub_nodes: list[str] = []
        for n in nodes:
            node_counter += 1
            nid = f"N{node_counter}"
            safe_name = n["name"].replace('"', "'")
            shape = "[" if n["kind"] == "function" else "(["
            shape_end = "]" if n["kind"] == "function" else "])"
            sub_nodes.append(f"    {nid}{shape}\"{safe_name}\"{shape_end}")
            node_id_map[f"{n['name']}|{n['file']}"] = nid

        group_id = group_key.replace("/", "_").replace("-", "_")
        lines.append(f"  subgraph {group_id}[\"{group_key}\"]")
        lines.extend(sub_nodes)
        lines.append("  end")

    # Cross-module edges only (avoid clutter)
    edge_lines: list[str] = []
    edge_set: set[tuple[int, int]] = set()

    for group_key, nodes in included_groups:
        for n in nodes:
            src_key = f"{n['name']}|{n['file']}"
            src_id = node_id_map.get(src_key)
            if not src_id:
                continue

            edges = conn.execute("""
                SELECT tgt.name, tgt.file_path
                FROM edges e
                JOIN nodes tgt ON e.target_node_id = tgt.id
                JOIN nodes src ON e.source_node_id = src.id
                WHERE src.name = ? AND src.file_path = ?
                  AND tgt.name != src.name
                  AND tgt.kind IN ('class', 'function')
                LIMIT 8
            """, (n["name"], n["file"])).fetchall()

            for tgt_name, tgt_file in edges:
                tgt_key = f"{tgt_name}|{tgt_file}"
                tgt_id = node_id_map.get(tgt_key)
                if not tgt_id:
                    continue
                # Only show cross-module edges
                if _module_key(n["file"]) == _module_key(tgt_file):
                    continue
                pair = (node_counter - len(included_groups) + list(included_groups).index((group_key, nodes)), node_counter - len(included_groups) + nodes.index(n))
                # Just use the IDs directly
                if (int(src_id[1:]), int(tgt_id[1:])) not in edge_set:
                    edge_set.add((int(src_id[1:]), int(tgt_id[1:])))
                    edge_lines.append(f"  {src_id} --> {tgt_id}")

    max_edges = max_nodes
    shown = 0
    for e in edge_lines[:max_edges]:
        lines.append(e)
        shown += 1
    if len(edge_lines) > shown:
        lines.append(f"  %% … {len(edge_lines) - shown} more cross-module edges")

    lines.append("```")
    lines.append("")
    lines.append(f"> **{included_count} symbols** in **{len(included_groups)} modules**")
    lines.append(f"> {total_nodes} total indexed symbols. {len(edge_lines)} cross-module call edges.")
    lines.append("> Paste into any Mermaid renderer (GitHub markdown, etc.).")
    lines.append("> Classes: `(...)`  Functions: `[...]`")

    conn.close()
    return "\n".join(lines)


def _build_file_stats(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Build per-file stats: classes, functions, methods, total symbols, LOC."""
    stats: dict[str, dict[str, Any]] = {}

    rows = conn.execute("""
        SELECT file_path,
               SUM(CASE WHEN kind='class' THEN 1 ELSE 0 END) as classes,
               SUM(CASE WHEN kind='function' THEN 1 ELSE 0 END) as funcs,
               SUM(CASE WHEN kind='method' THEN 1 ELSE 0 END) as methods,
               COUNT(*) as total,
               MAX(end_line) as loc
        FROM nodes
        GROUP BY file_path
    """).fetchall()
    for fp, classes, funcs, methods, total, loc in rows:
        stats[fp] = {
            "classes": classes,
            "funcs": funcs,
            "methods": methods,
            "total": total,
            "loc": loc or 0,
        }

    # Add language and size from files table
    rows2 = conn.execute("SELECT path, language, size FROM files").fetchall()
    for path, lang, size in rows2:
        if path in stats:
            stats[path]["language"] = lang
            stats[path]["size"] = size
        else:
            stats[path] = {
                "classes": 0, "funcs": 0, "methods": 0,
                "total": 0, "loc": 0, "language": lang, "size": size,
            }

    return stats


def _build_tree(files: list[str]) -> dict:
    """Build a nested dict tree from file paths."""
    tree: dict = {}
    for path in sorted(files):
        parts = path.split("/")
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
    return tree


def _generate_ascii_tree(kg: KnowledgeGraph) -> str:
    """Generate an ASCII-only directory tree (no Unicode, no Rich).

    Uses ``|-- `` and ```-- `` connectors — safe for any terminal or log file.
    """
    conn = kg.db._connect()
    files = conn.execute("SELECT path FROM files ORDER BY path").fetchall()
    file_list = [r[0] for r in files]
    stats = _build_file_stats(conn)
    tree = _build_tree(file_list)

    lines: list[str] = []
    lines.append("# Project Structure")
    lines.append("")

    def _render(subtree: dict, prefix: str = "", path_so_far: str = "") -> None:
        items = list(subtree.items())
        for i, (name, sub) in enumerate(items):
            connector = "`-- " if i == len(items) - 1 else "|-- "
            child_path = f"{path_so_far}/{name}" if path_so_far else name

            if sub:
                lines.append(f"{prefix}{connector}{name}/")
                extension = "    " if i == len(items) - 1 else "|   "
                _render(sub, prefix + extension, child_path)
            else:
                info = stats.get(child_path, {})
                parts = []
                if info.get("classes"):
                    parts.append(f"{info['classes']} classes")
                if info.get("funcs"):
                    parts.append(f"{info['funcs']} functions")
                if info.get("methods"):
                    parts.append(f"{info['methods']} methods")
                suffix = f"  ({', '.join(parts)})" if parts else ""
                lines.append(f"{prefix}{connector}{name}{suffix}")

    _render(tree)

    total_classes = sum(s["classes"] for s in stats.values())
    total_funcs = sum(s["funcs"] for s in stats.values())
    total_methods = sum(s["methods"] for s in stats.values())
    total_loc = sum(s["loc"] for s in stats.values())
    lines.append("")
    lines.append(f"Total: {len(file_list)} files  |  "
                 f"{total_classes} classes  {total_funcs} functions  "
                 f"{total_methods} methods  |  ~{total_loc} LOC")

    return "\n".join(lines)


def _generate_tree_text(kg: KnowledgeGraph) -> str:
    """Generate a plain-text directory tree (for --output file)."""
    conn = kg.db._connect()
    files = conn.execute("SELECT path FROM files ORDER BY path").fetchall()
    file_list = [r[0] for r in files]
    stats = _build_file_stats(conn)
    tree = _build_tree(file_list)

    lines: list[str] = []
    lines.append("# Project Structure")
    lines.append("")

    def _render(subtree: dict, prefix: str = "", path_so_far: str = "") -> None:
        items = list(subtree.items())
        for i, (name, sub) in enumerate(items):
            connector = "└── " if i == len(items) - 1 else "├── "
            child_path = f"{path_so_far}/{name}" if path_so_far else name

            if sub:
                lines.append(f"{prefix}{connector}{name}/")
                extension = "    " if i == len(items) - 1 else "│   "
                _render(sub, prefix + extension, child_path)
            else:
                info = stats.get(child_path, {})
                parts = []
                if info.get("classes"):
                    parts.append(f"{info['classes']} classes")
                if info.get("funcs"):
                    parts.append(f"{info['funcs']} functions")
                if info.get("methods"):
                    parts.append(f"{info['methods']} methods")
                suffix = f"  ({', '.join(parts)})" if parts else ""
                lines.append(f"{prefix}{connector}{name}{suffix}")

    _render(tree)

    # Summary
    total_classes = sum(s["classes"] for s in stats.values())
    total_funcs = sum(s["funcs"] for s in stats.values())
    total_methods = sum(s["methods"] for s in stats.values())
    total_loc = sum(s["loc"] for s in stats.values())
    lines.append("")
    lines.append(f"Total: {len(file_list)} files  |  "
                 f"{total_classes} classes  {total_funcs} functions  "
                 f"{total_methods} methods  |  ~{total_loc} LOC")

    return "\n".join(lines)


def _display_rich_tree(kg: KnowledgeGraph) -> None:
    """Display an enhanced directory tree with Rich formatting."""

    conn = kg.db._connect()
    files = conn.execute("SELECT path FROM files ORDER BY path").fetchall()
    file_list = [r[0] for r in files]
    stats = _build_file_stats(conn)
    tree = _build_tree(file_list)

    # ── Dashboard panel ──────────────────────────────────────────────
    total_classes = sum(s["classes"] for s in stats.values())
    total_funcs = sum(s["funcs"] for s in stats.values())
    total_methods = sum(s["methods"] for s in stats.values())
    total_loc = sum(s["loc"] for s in stats.values())
    total_nodes = total_classes + total_funcs + total_methods
    languages: dict[str, int] = {}
    for s in stats.values():
        lang = s.get("language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1
    lang_summary = "  ".join(f"[cyan]{lang}[/] x{cnt}" for lang, cnt in sorted(languages.items(), key=lambda x: -x[1]))

    dashboard = (
        f"[bold]Project Overview[/]\n\n"
        f"  Files:       [bold]{len(file_list)}[/]\n"
        f"  Symbols:     [bold]{total_nodes}[/] total  "
        f"([yellow]{total_classes}[/] classes  "
        f"[green]{total_funcs}[/] functions  "
        f"[blue]{total_methods}[/] methods)\n"
        f"  Lines:       ~[bold]{total_loc}[/] LOC\n"
        f"  Languages:   {lang_summary}"
    )
    console.panel(dashboard, title="📊  Project Dashboard")

    # ── Enhanced directory tree ───────────────────────────────────────
    console.section("Directory Structure")

    def _render(subtree: dict, prefix: str = "", path_so_far: str = "") -> None:
        items = list(subtree.items())
        for i, (name, sub) in enumerate(items):
            connector = "└── " if i == len(items) - 1 else "├── "
            child_path = f"{path_so_far}/{name}" if path_so_far else name

            if sub:
                console.print(f"{prefix}{connector}[bold]{name}[/]/")
                extension = "    " if i == len(items) - 1 else "│   "
                _render(sub, prefix + extension, child_path)
            else:
                info = stats.get(child_path, {})
                # Build a compact info string
                parts = []
                if info.get("classes"):
                    parts.append(f"[yellow]{info['classes']}c[/]")
                if info.get("funcs"):
                    parts.append(f"[green]{info['funcs']}f[/]")
                if info.get("methods"):
                    parts.append(f"[blue]{info['methods']}m[/]")
                suffix = f"  [dim]({' '.join(parts)})[/]" if parts else ""

                lang = info.get("language", "")
                lang_badge = f"[[cyan]{lang}[/]]" if lang else ""

                loc = info.get("loc", 0)
                loc_str = f"[dim]{loc} LOC[/]" if loc else ""

                console.print(f"{prefix}{connector}{name}  {lang_badge} {loc_str}{suffix}")

    _render(tree)

    # ── Language summary table ────────────────────────────────────────
    console.section("Language Breakdown")
    lang_rows = []
    for lang, cnt in sorted(languages.items(), key=lambda x: -x[1]):
        lang_loc = sum(s["loc"] for s in stats.values() if s.get("language") == lang)
        lang_syms = sum(
            s["classes"] + s["funcs"] + s["methods"]
            for s in stats.values() if s.get("language") == lang
        )
        # Unicode bar
        pct = lang_loc / total_loc * 100 if total_loc else 0
        bar_len = max(1, int(pct / 5))
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lang_rows.append([lang, str(cnt), f"~{lang_loc}", f"{pct:.0f}%", bar])

    console.table(
        "Languages",
        ["Language", "Files", "LOC", "%", "Distribution"],
        lang_rows,
    )


def _print_graph_results(
    results: list[dict[str, Any]],
    show_depth_label: bool = False,
) -> None:
    """Render callers/callees/impact results with depth-based visual indentation."""
    _NODE_COLORS = ["#00C9A7", "#00A8E8", "#845EC2", "#FFC75F"]

    for r in results:
        d = r.get("depth", 0)
        color = _NODE_COLORS[min(d, len(_NODE_COLORS) - 1)]
        indent = "   " * d
        connector = "└─ " if d > 0 else "   "
        depth_tag = f" [dim]depth {d}[/]" if show_depth_label else ""
        console.print(
            f"  {indent}{connector}[{color}]◉[/] [bold]{r['name']}[/]"
            f" [dim]({r['kind']})[/]"
            f"  [dim]{r['file_path']}:{r['line']}[/]{depth_tag}"
        )


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
