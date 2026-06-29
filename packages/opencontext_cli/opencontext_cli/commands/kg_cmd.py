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

    kg_node = kg_sub.add_parser(
        "node",
        help="Get a symbol's details, and with --code its EXACT source in one call.",
        description=(
            "One-call surgical locate: the KG knows the symbol's extent, so `--code` "
            "returns just its source — replacing 'search to find it, then Read the "
            "whole file'. On a large file that is far fewer tokens than reading around "
            "the hit."
        ),
    )
    kg_node.add_argument("symbol", help="Symbol name.")
    kg_node.add_argument(
        "--code", action="store_true", help="Include the symbol's exact source code."
    )
    kg_node.add_argument("--json", action="store_true")

    kg_sub.add_parser("status", help="Check index status.")

    from opencontext_cli.commands.migration_cmd import add_migrate_subparser

    add_migrate_subparser(kg_sub, "kg")
    kg_sub.add_parser("rebuild", help="Rebuild the KG from source (`index .`).")

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
    kg_view.add_argument("--max-nodes", type=int, default=50, help="Max nodes in Mermaid graph.")
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

    if command == "migrate":
        from opencontext_cli.commands.migration_cmd import handle_migrate

        raise SystemExit(handle_migrate("kg", args))
    if command == "rebuild":
        print("KG rebuild: run `opencontext index .` to rebuild the graph from source.")
        return
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

    # Graph-reading commands need an index; if it's empty, say so rather than
    # returning a bare "No results" (indistinguishable from "indexed, no match").
    if command in {"search", "query", "callers", "callees", "impact", "node"}:
        try:
            if kg.get_stats().get("nodes", 0) == 0 and not json_output:
                console.print("[yellow]No knowledge graph found for this project.[/]")
                console.print("  Run [cyan]opencontext index .[/] first to build it.")
                return
        except Exception:
            pass

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

    elif command == "node":
        include_code = getattr(args, "code", False)
        conn = kg.db._connect()
        rows = conn.execute(
            "SELECT name, kind, file_path, line, end_line, signature, docstring "
            "FROM nodes WHERE name = ? ORDER BY line LIMIT 1",
            (symbol,),
        ).fetchall()
        if not rows:
            if json_output:
                print(json.dumps({"error": f"Symbol not found: {symbol}"}))
            else:
                console.error(f"Symbol not found: {symbol}")
        else:
            r = rows[0]
            info: dict[str, Any] = {
                "name": r["name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "line": r["line"],
                "end_line": r["end_line"],
                "signature": r["signature"],
                "docstring": r["docstring"],
            }
            if include_code and r["line"] and r["end_line"]:
                try:
                    # KG file paths are relative to the indexed project root; derive it
                    # from the db location (<root>/.storage/opencontext/context_graph.db)
                    # so --code reads the real file even when cwd is a subdirectory.
                    root = kg.db.db_path.resolve().parent.parent.parent
                    src = (root / r["file_path"]).read_text(encoding="utf-8", errors="ignore")
                    info["code"] = "\n".join(src.splitlines()[r["line"] - 1 : r["end_line"]])
                except OSError:
                    pass
            if json_output:
                print(json.dumps(info, indent=2))
            else:
                console.header(f"Node: {info['name']} ({info['kind']})")
                console.print(f"  [dim]{info['file']}:{info['line']}[/]")
                if info.get("signature"):
                    console.print(f"  {info['signature']}")
                if info.get("code"):
                    console.print(info["code"])

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
        source_name = getattr(args, "source", "")
        target_name = getattr(args, "target", "")
        max_depth = getattr(args, "max_depth", 10)
        json_output = getattr(args, "json", False)
        console.header(f"Trace: {source_name} -> {target_name}")

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

            print(
                _json.dumps(
                    {
                        "found": result.found,
                        "path": result.path,
                        "depth_exceeded": result.depth_exceeded,
                        "hops": result.hops,
                    },
                    indent=2,
                )
            )
        elif result.found:
            console.print(
                f"[green]Found path[/] ([bold]{result.hops}[/] hop{'s' if result.hops != 1 else ''})"
            )
            for i, node in enumerate(result.path):
                console.print(
                    f"  {i + 1}. [bold]{node['name']}[/] ({node['file_path']}:{node['line']})"
                )
        else:
            msg = "Maximum depth reached." if result.depth_exceeded else "No path exists."
            console.print(f"[yellow]{msg}[/]")

    elif command == "view":
        max_nodes = getattr(args, "max_nodes", 50)
        output_path = getattr(args, "output", None)
        use_tree = getattr(args, "tree", False)
        fmt = getattr(args, "format", None)

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
                print(output)
            else:
                _display_rich_tree(kg)
        else:
            label = "Mermaid graph"
            # Gather all data BEFORE mermaid generation closes the DB connection
            import json as _json
            from datetime import datetime as _dt

            _stats = kg.get_stats()
            _tree_data = _build_tree_data(kg, max_nodes)
            output = _generate_mermaid_graph(kg, max_nodes)
            if output_path:
                with open(output_path, "w") as f:
                    f.write(output)
                console.print(f"  ✓ {label} saved to [cyan]{output_path}[/]")
            else:
                console.print(output)
                _total_nodes = _stats.get("nodes", 0)
                _total_files = _stats.get("files", 0)
                _total_edges = _stats.get("edges", 0)
                _generated_at = _dt.now().strftime("%Y-%m-%d %H:%M")
                _tree_json = _json.dumps(_tree_data, ensure_ascii=False)

                html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knowledge Graph — OpenContext</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#080E1A;--surface:#0D1626;--border:#1A2840;
  --teal:#00C9A7;--blue:#00A8E8;--purple:#845EC2;
  --text:#A8C0D8;--muted:#3A5570;
  --font:ui-monospace,'Cascadia Code','Fira Code',Consolas,monospace;
}}
html,body{{height:100%;overflow:hidden}}
body{{background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px;display:flex;flex-direction:column}}
header{{display:flex;align-items:center;gap:1.5rem;padding:1rem 2rem;border-bottom:1px solid var(--border);background:#060B14;flex-shrink:0}}
.logo-art{{font-size:0.7rem;line-height:1.5;white-space:pre;color:var(--teal);user-select:none}}
.logo-art .b{{color:var(--blue)}}.logo-art .p{{color:var(--purple)}}.logo-art .d{{color:var(--muted)}}
.header-info h1{{font-size:1rem;font-weight:700;color:#E0EFFF;letter-spacing:.03em}}
.header-info p{{font-size:.72rem;color:var(--muted);margin-top:.2rem}}
.stats-bar{{display:flex;gap:.75rem;padding:.7rem 2rem;border-bottom:1px solid var(--border);background:var(--surface);flex-shrink:0;flex-wrap:wrap;align-items:center}}
.chip{{display:inline-flex;align-items:center;gap:.4rem;padding:.25rem .8rem;border-radius:2rem;font-size:.74rem;font-weight:500;border:1px solid currentColor}}
.chip-teal{{color:var(--teal);background:rgba(0,201,167,.07)}}
.chip-blue{{color:var(--blue);background:rgba(0,168,232,.07)}}
.chip-purple{{color:var(--purple);background:rgba(132,94,194,.07)}}
.chip-dot{{width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0}}
.hint{{margin-left:auto;font-size:.7rem;color:var(--muted);font-style:italic}}
#tree-wrap{{flex:1;overflow:hidden;position:relative}}
#tree-svg{{width:100%;height:100%;display:block;cursor:grab}}
#tree-svg:active{{cursor:grabbing}}
.nd{{font-family:var(--font);cursor:default}}
.nd.clickable{{cursor:pointer}}
.nd circle{{transition:r .18s,fill .18s,stroke .18s}}
.nd.clickable:hover circle{{filter:brightness(1.3)}}
.nd text{{font-size:12px;dominant-baseline:central;pointer-events:none;transition:opacity .2s}}
.nd .nd-pill{{rx:4;transition:fill .18s;pointer-events:all}}
.nd.clickable:hover .nd-pill{{fill:rgba(255,255,255,0.05)}}
.lk{{fill:none;stroke:#1A3050;stroke-width:1.5;stroke-opacity:.8}}
.toolbar{{display:flex;gap:.5rem;margin-left:auto;align-items:center}}
.btn{{padding:.2rem .75rem;border-radius:.3rem;border:1px solid var(--border);background:var(--surface);color:var(--text);font-family:var(--font);font-size:.72rem;cursor:pointer;transition:border-color .15s,color .15s}}
.btn:hover{{border-color:var(--teal);color:var(--teal)}}
footer{{padding:.5rem 2rem;border-top:1px solid var(--border);font-size:.7rem;color:var(--muted);display:flex;justify-content:space-between;flex-shrink:0;align-items:center}}
.leg{{display:flex;gap:1.2rem;align-items:center;flex-wrap:wrap}}
.leg-dot{{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:.3rem;vertical-align:middle}}
</style>
</head>
<body>
<header>
  <div class="logo-art"><span>◉</span><span class="d">──</span><span class="b">◉</span><span class="d">──</span><span class="p">◉</span>
<span class="d">│</span>     <span class="p">│</span>
<span>◉</span><span class="d">──</span><span class="b">◉  </span><span class="p">◉</span>
<span class="d">│  </span><span class="b">│</span></div>
  <div class="header-info">
    <h1>Knowledge Graph</h1>
    <p>OpenContext Runtime &mdash; project structure</p>
  </div>
</header>
<div class="stats-bar">
  <span class="chip chip-teal"><span class="chip-dot"></span>{_total_nodes:,} symbols</span>
  <span class="chip chip-blue"><span class="chip-dot"></span>{_total_files:,} files</span>
  <span class="chip chip-purple"><span class="chip-dot"></span>{_total_edges:,} call edges</span>
  <div class="toolbar">
    <button class="btn" id="btn-expand">Expand all</button>
    <button class="btn" id="btn-collapse">Collapse all</button>
    <button class="btn" id="btn-fit">Fit view</button>
  </div>
</div>
<div id="tree-wrap"><svg id="tree-svg"></svg></div>
<footer>
  <div class="leg">
    <span><span class="leg-dot" style="background:#00C9A7"></span>project root</span>
    <span><span class="leg-dot" style="background:#00A8E8"></span>module <span style="color:var(--muted);font-size:.65rem">(click to collapse)</span></span>
    <span><span class="leg-dot" style="background:#0A1828;border:1px solid #00A8E8;border-radius:50%"></span>class</span>
    <span><span class="leg-dot" style="background:#0A1820;border:1px solid #00C9A7;border-radius:50%"></span>function</span>
    <span style="color:var(--muted)">Scroll to zoom &nbsp;·&nbsp; Drag to pan</span>
  </div>
  <span>Generated {_generated_at}</span>
</footer>
<script>
(function(){{
const DATA = {_tree_json};
const C = {{
  root:    {{fill:'#00C9A7', stroke:'#009A80', text:'#060B14', r:12}},
  module:  {{fill:'#0D1F36', stroke:'#00A8E8', text:'#7DC8F8', r:10}},
  class:   {{fill:'#0A1828', stroke:'#244A70', text:'#59B0E8', r:6}},
  function:{{fill:'#0A1820', stroke:'#1E4030', text:'#36C9A2', r:6}},
}};

const svg = d3.select('#tree-svg');
const g   = svg.append('g').attr('class','root-g');
const zoom = d3.zoom().scaleExtent([0.05,8]).on('zoom',e=>g.attr('transform',e.transform));
svg.call(zoom).on('dblclick.zoom',null);

const tree = d3.tree().nodeSize([38, 290]);
const root = d3.hierarchy(DATA);
let uid=0;

function diagonal(s,d){{
  return `M${{s.y}},${{s.x}}C${{(s.y+d.y)/2}},${{s.x}} ${{(s.y+d.y)/2}},${{d.x}} ${{d.y}},${{d.x}}`;
}}
function sy(d){{ return d.y0!==undefined?d.y0:d.y; }}
function sx(d){{ return d.x0!==undefined?d.x0:d.x; }}

function isToggleable(d){{ return !!(d.children||d._children); }}

function update(src, dur){{
  const duration = dur!==undefined?dur:280;
  tree(root);
  const nodes = root.descendants();
  const links = root.links();

  // links
  const lk = g.selectAll('path.lk').data(links, d=>d.target.id);
  lk.enter().insert('path','g').attr('class','lk')
    .attr('d',()=>diagonal({{y:sy(src),x:sx(src)}},{{y:sy(src),x:sx(src)}}))
    .merge(lk).transition().duration(duration).attr('d',d=>diagonal(d.source,d.target));
  lk.exit().transition().duration(duration)
    .attr('d',()=>diagonal({{y:src.y,x:src.x}},{{y:src.y,x:src.x}})).remove();

  // nodes
  const nd = g.selectAll('g.nd').data(nodes, d=>d.id||(d.id=++uid));
  const enter = nd.enter().append('g').attr('class','nd')
    .attr('transform', d=>`translate(${{sy(src)}},${{sx(src)}})`);

  enter.append('title');
  // invisible wider hit-area rect
  enter.append('rect').attr('class','nd-pill')
    .attr('y',-14).attr('height',28).attr('fill','transparent');
  enter.append('circle').attr('r',0);
  // toggle indicator for module nodes
  enter.append('text').attr('class','nd-toggle')
    .attr('dominant-baseline','central')
    .style('pointer-events','none')
    .style('font-size','10px')
    .style('user-select','none');
  enter.append('text').attr('class','nd-label').style('opacity',0);

  // click on the pill or circle
  enter.on('click',(e,d)=>{{
    if(!isToggleable(d)) return;
    if(d.children){{d._children=d.children;d.children=null;}}
    else{{d.children=d._children;d._children=null;}}
    update(d);
  }});

  const all = nd.merge(enter);
  all.classed('clickable', d=>isToggleable(d));
  all.transition().duration(duration).attr('transform',d=>`translate(${{d.y}},${{d.x}})`);

  all.select('title').text(d=>
    d.data.type==='module'?d.data.path:
    d.data.file?`${{d.data.file}}:${{d.data.line||''}}`:d.data.name
  );

  // pill width
  all.select('.nd-pill')
    .attr('x', d=>d.depth===0?-80:d.children||d._children?-170:-10)
    .attr('width', d=>d.depth===0?180:200)
    .attr('rx', 4);

  all.select('circle')
    .attr('r', d=>(C[d.data.type]||C.function).r)
    .style('fill',   d=>(C[d.data.type]||C.function).fill)
    .style('stroke', d=>(C[d.data.type]||C.function).stroke)
    .style('stroke-width', d=>d.data.type==='root'?2.5:1.8);

  // expand/collapse indicator
  all.select('.nd-toggle')
    .attr('x', d=>(d.children||d._children)?-18:0)
    .attr('text-anchor','middle')
    .text(d=>{{
      if(d.data.type!=='module') return '';
      return d.children?'▾':'▸';
    }})
    .style('fill','#00A8E8')
    .style('opacity', d=>d.data.type==='module'?1:0);

  all.select('.nd-label')
    .attr('x', d=>d.depth===0?18:d.children||d._children?-22:16)
    .attr('text-anchor', d=>d.depth===0?'start':d.children||d._children?'end':'start')
    .text(d=>{{
      if(d.data.type==='module'){{
        const open = !!d.children;
        const n = (d.children||d._children||[]).length;
        return `${{d.data.name}}  (${{n}})`;
      }}
      return d.data.name;
    }})
    .style('fill',   d=>(C[d.data.type]||C.function).text)
    .style('font-size',d=>d.data.type==='root'?'14px':d.data.type==='module'?'13px':'11.5px')
    .style('font-weight',d=>['root','module'].includes(d.data.type)?'600':'400')
    .transition().duration(duration).style('opacity',1);

  nd.exit().transition().duration(duration)
    .attr('transform',`translate(${{src.y}},${{src.x}})`)
    .style('opacity',0).remove();

  nodes.forEach(d=>{{d.x0=d.x;d.y0=d.y;}});
}}

function zoomFit(dur){{
  const wrap = document.getElementById('tree-wrap');
  const W=wrap.clientWidth, H=wrap.clientHeight;
  const bb = g.node().getBBox();
  if(!bb.width||!bb.height) return;
  const pad=60;
  const scale = Math.min((W-pad*2)/bb.width, (H-pad*2)/bb.height, 1.4);
  const tx = pad - bb.x*scale + (W - bb.width*scale - pad*2)/2;
  const ty = pad - bb.y*scale + (H - bb.height*scale - pad*2)/2;
  svg.transition().duration(dur||400)
    .call(zoom.transform, d3.zoomIdentity.translate(tx,ty).scale(scale));
}}

function expandAll(){{
  root.each(d=>{{ if(d._children){{d.children=d._children;d._children=null;}} }});
  update(root,320);
  setTimeout(zoomFit,380);
}}
function collapseAll(){{
  root.descendants().filter(d=>d.depth===1).forEach(d=>{{
    if(d.children){{d._children=d.children;d.children=null;}}
  }});
  update(root,320);
  setTimeout(zoomFit,380);
}}

document.getElementById('btn-expand').addEventListener('click',expandAll);
document.getElementById('btn-collapse').addEventListener('click',collapseAll);
document.getElementById('btn-fit').addEventListener('click',()=>zoomFit(400));

// Start fully expanded
root.x0=0; root.y0=0;
update(root, 0);
setTimeout(zoomFit, 80);
}})();
</script>
</body>
</html>"""
                # Write into the managed (gitignored) workspace dir, not the repo root.
                html_dir = os.path.join(os.getcwd(), ".opencontext")
                os.makedirs(html_dir, exist_ok=True)
                html_path = os.path.join(html_dir, "kg-view.html")
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


def _build_tree_data(kg: KnowledgeGraph, max_nodes: int = 50) -> dict[str, Any]:
    """Build a JSON-serializable hierarchy for the D3 tree viewer.

    Returns: project root -> module nodes -> symbol leaves.
    Does NOT close the DB connection (caller is responsible).
    """
    import collections
    from pathlib import Path

    conn = kg.db._connect()
    rows = conn.execute("""
        SELECT n.name, n.kind, n.file_path, n.line
        FROM nodes n
        WHERE n.kind IN ('class', 'function')
          AND (n.container IS NULL OR n.container = '')
        ORDER BY n.file_path, n.kind, n.name
    """).fetchall()

    def _module_key(path: str) -> str:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "packages":
            return f"{parts[0]}/{parts[1]}"
        return parts[0]

    dir_groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for name, kind, file_path, line in rows:
        dir_groups[_module_key(file_path)].append(
            {"name": name, "kind": kind, "file": file_path, "line": line or 0}
        )

    sorted_groups = sorted(dir_groups.items(), key=lambda x: -len(x[1]))
    num_groups = min(len(sorted_groups), max(5, max_nodes // 5))
    per_group = max(2, max_nodes // num_groups)
    included_groups: list[tuple[str, list[dict[str, Any]]]] = []
    included_count = 0
    for i, (group_key, nodes) in enumerate(sorted_groups):
        if i >= num_groups:
            break
        share = min(per_group, len(nodes))
        if included_count + share > max_nodes:
            share = max_nodes - included_count
        if share <= 0:
            break
        included_groups.append((group_key, nodes[:share]))
        included_count += share

    project_name = Path.cwd().name
    return {
        "name": project_name,
        "type": "root",
        "children": [
            {
                "name": group_key.split("/")[-1] if "/" in group_key else group_key,
                "type": "module",
                "path": group_key,
                "total": len(dir_groups[group_key]),
                "children": [
                    {
                        "name": n["name"],
                        "type": n["kind"],
                        "file": n["file"],
                        "line": n["line"],
                    }
                    for n in nodes
                ],
            }
            for group_key, nodes in included_groups
        ],
    }


def _generate_mermaid_graph(kg: KnowledgeGraph, max_nodes: int = 50) -> str:
    """Generate a Mermaid tree graph: project root -> modules -> symbols.

    Hierarchy: ROOT node at top -> module header nodes -> class/function leaves.
    Cross-module call edges are shown as dashed arrows.
    """
    import collections
    from pathlib import Path

    conn = kg.db._connect()

    rows = conn.execute("""
        SELECT n.name, n.kind, n.file_path
        FROM nodes n
        WHERE n.kind IN ('class', 'function')
          AND (n.container IS NULL OR n.container = '')
        ORDER BY n.file_path, n.kind, n.name
    """).fetchall()

    def _module_key(path: str) -> str:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "packages":
            return f"{parts[0]}/{parts[1]}"
        return parts[0]

    dir_groups: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for name, kind, file_path in rows:
        dir_groups[_module_key(file_path)].append({"name": name, "kind": kind, "file": file_path})

    total_nodes = sum(len(v) for v in dir_groups.values())

    sorted_groups = sorted(dir_groups.items(), key=lambda x: -len(x[1]))
    num_groups = min(len(sorted_groups), max(5, max_nodes // 5))
    per_group = max(2, max_nodes // num_groups)
    included_groups: list[tuple[str, list[dict[str, str]]]] = []
    included_count = 0
    for i, (group_key, nodes) in enumerate(sorted_groups):
        if i >= num_groups:
            break
        share = min(per_group, len(nodes))
        if included_count + share > max_nodes:
            share = max_nodes - included_count
        if share <= 0:
            break
        included_groups.append((group_key, nodes[:share]))
        included_count += share

    node_id_map: dict[str, str] = {}
    node_counter = 0
    project_name = Path.cwd().name

    lines: list[str] = []
    lines.append("```mermaid")
    lines.append("flowchart TD")
    lines.append("  %% Project structure — auto-generated from knowledge graph")
    lines.append(
        f"  %% {included_count} symbols from {len(included_groups)} modules (max {max_nodes})"
    )
    lines.append("")
    # Project root node at the top
    safe_proj = project_name.replace('"', "'")
    lines.append(f'  ROOT(["◎ {safe_proj}"]):::root')
    lines.append("")

    for group_idx, (group_key, nodes) in enumerate(included_groups):
        group_id = group_key.replace("/", "_").replace("-", "_")
        mod_hdr_id = f"MH{group_idx}"
        short_name = group_key.split("/")[-1] if "/" in group_key else group_key
        safe_short = short_name.replace('"', "'")
        safe_group = group_key.replace('"', "'")

        sym_nodes: list[str] = []
        hdr_edges: list[str] = []
        for n in nodes:
            node_counter += 1
            nid = f"N{node_counter}"
            safe_name = n["name"].replace('"', "'")
            if n["kind"] == "class":
                sym_nodes.append(f'    {nid}(["{safe_name}"]):::cls')
            else:
                sym_nodes.append(f'    {nid}["{safe_name}"]:::fn')
            hdr_edges.append(f"    {mod_hdr_id} --> {nid}")
            node_id_map[f"{n['name']}|{n['file']}"] = nid

        lines.append(f'  subgraph {group_id}["{safe_group}"]')
        lines.append(f'    {mod_hdr_id}["{safe_short}"]:::mod_hdr')
        lines.extend(sym_nodes)
        lines.extend(hdr_edges)
        lines.append("  end")
        lines.append(f"  ROOT --> {mod_hdr_id}")
        lines.append("")

    # Cross-module call edges as dashed arrows
    edge_lines: list[str] = []
    edge_set: set[tuple[str, str]] = set()

    for _group_key, nodes in included_groups:
        for n in nodes:
            src_key = f"{n['name']}|{n['file']}"
            src_id = node_id_map.get(src_key)
            if not src_id:
                continue
            edges = conn.execute(
                """
                SELECT tgt.name, tgt.file_path
                FROM edges e
                JOIN nodes tgt ON e.target_node_id = tgt.id
                JOIN nodes src ON e.source_node_id = src.id
                WHERE src.name = ? AND src.file_path = ?
                  AND tgt.name != src.name
                  AND tgt.kind IN ('class', 'function')
                LIMIT 8
            """,
                (n["name"], n["file"]),
            ).fetchall()

            for tgt_name, tgt_file in edges:
                tgt_key = f"{tgt_name}|{tgt_file}"
                tgt_id = node_id_map.get(tgt_key)
                if not tgt_id:
                    continue
                if _module_key(n["file"]) == _module_key(tgt_file):
                    continue
                pair = (src_id, tgt_id)
                if pair not in edge_set:
                    edge_set.add(pair)
                    edge_lines.append(f"  {src_id} -.-> {tgt_id}")

    shown = 0
    for e in edge_lines[:max_nodes]:
        lines.append(e)
        shown += 1
    if len(edge_lines) > shown:
        lines.append(f"  %% ... {len(edge_lines) - shown} more cross-module call edges")

    lines.append("")
    lines.append("  classDef root fill:#00C9A7,color:#060B14,stroke:#00C9A7,font-weight:bold,rx:8")
    lines.append("  classDef mod_hdr fill:#0F1E30,color:#00A8E8,stroke:#00A8E8,font-weight:bold")
    lines.append("  classDef cls fill:#0A1520,color:#00A8E8,stroke:#1A2840")
    lines.append("  classDef fn fill:#0A1520,color:#00C9A7,stroke:#1A2840")
    lines.append("```")
    lines.append("")
    lines.append(f"> **{included_count} symbols** in **{len(included_groups)} modules**")
    lines.append(
        f"> {total_nodes} total indexed symbols. {len(edge_lines)} cross-module call edges."
    )
    lines.append("> Paste into any Mermaid renderer (GitHub markdown, etc.).")
    lines.append(
        "> Classes: `(...)` &nbsp; Functions: `[...]` &nbsp; Dashed arrows: cross-module calls"
    )

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
                "classes": 0,
                "funcs": 0,
                "methods": 0,
                "total": 0,
                "loc": 0,
                "language": lang,
                "size": size,
            }

    return stats


def _build_tree(files: list[str]) -> dict[str, Any]:
    """Build a nested dict tree from file paths."""
    tree: dict[str, Any] = {}
    for path in sorted(files):
        parts = path.split("/")
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
    return tree


def _render_tree(kg: KnowledgeGraph, *, last: str, mid: str, vert: str) -> str:
    """Render the project directory tree with the given branch connectors.

    ``last``/``mid`` are the leaf / non-leaf connectors and ``vert`` the vertical
    extension — pass ASCII (```-- ``/``|-- ``/``|   ``) or Unicode box-drawing
    (``└── ``/``├── ``/``│   ``). The traversal and summary are otherwise identical.
    """
    conn = kg.db._connect()
    files = conn.execute("SELECT path FROM files ORDER BY path").fetchall()
    file_list = [r[0] for r in files]
    stats = _build_file_stats(conn)
    tree = _build_tree(file_list)

    lines: list[str] = ["# Project Structure", ""]

    def _render(subtree: dict[str, Any], prefix: str = "", path_so_far: str = "") -> None:
        items = list(subtree.items())
        for i, (name, sub) in enumerate(items):
            connector = last if i == len(items) - 1 else mid
            child_path = f"{path_so_far}/{name}" if path_so_far else name

            if sub:
                lines.append(f"{prefix}{connector}{name}/")
                extension = "    " if i == len(items) - 1 else vert
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
    lines.append(
        f"Total: {len(file_list)} files  |  "
        f"{total_classes} classes  {total_funcs} functions  "
        f"{total_methods} methods  |  ~{total_loc} LOC"
    )

    return "\n".join(lines)


def _generate_ascii_tree(kg: KnowledgeGraph) -> str:
    """ASCII-only directory tree (no Unicode/Rich) — safe for any terminal/log."""
    return _render_tree(kg, last="`-- ", mid="|-- ", vert="|   ")


def _generate_tree_text(kg: KnowledgeGraph) -> str:
    """Plain-text directory tree (Unicode box-drawing) for the ``--output`` file."""
    return _render_tree(kg, last="└── ", mid="├── ", vert="│   ")


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
    lang_summary = "  ".join(
        f"[cyan]{lang}[/] x{cnt}" for lang, cnt in sorted(languages.items(), key=lambda x: -x[1])
    )

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

    def _render(subtree: dict[str, Any], prefix: str = "", path_so_far: str = "") -> None:
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
