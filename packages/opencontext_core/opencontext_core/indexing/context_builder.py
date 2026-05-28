"""Context builder for AI tasks.

Builds relevant code context for a given task/query using the knowledge graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.impact_analysis import ImpactAnalyzer


@dataclass
class ContextNode:
    """A node in the built context."""

    name: str
    kind: str
    file_path: str
    line: int
    source_code: str = ""
    relevance_score: float = 0.0
    relationships: list[str] = field(default_factory=list)


@dataclass
class BuiltContext:
    """Result of building context for a task."""

    task: str
    nodes: list[ContextNode]
    total_tokens_estimate: int
    format: str
    coverage: dict[str, Any]


class ContextBuilder:
    """Builds optimized code context for AI tasks.

    Uses the knowledge graph to find relevant symbols, their relationships,
    and assembles them into a token-efficient context pack.
    """

    def __init__(
        self,
        db_path: str | Path = ".storage/opencontext/codegraph.db",
    ) -> None:
        self.db = GraphDatabase(db_path=db_path)
        self.db.init_schema()
        self.call_graph = CallGraphAnalyzer(db=self.db)
        self.impact = ImpactAnalyzer(db=self.db)

    def build_context(
        self,
        task: str,
        max_nodes: int = 20,
        include_code: bool = True,
        format: str = "markdown",
        root: str | Path = ".",
    ) -> BuiltContext:
        """Build relevant code context for a task.

        Args:
            task: Task description or query.
            max_nodes: Maximum number of nodes to include.
            include_code: Whether to include source code snippets.
            format: Output format (markdown, json, xml).
            root: Project root for file resolution.

        Returns:
            BuiltContext with assembled nodes.
        """

        root_path = Path(root).resolve()
        nodes: list[ContextNode] = []
        seen_ids: set[int] = set()

        # Step 1: Search for symbols matching the task
        search_results = self.db.search_fts(task, limit=max_nodes // 2)

        for result in search_results:
            node_id = result.get("id", 0)
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            node = self.db.get_node_by_id(node_id)
            if node is None:
                continue

            source_code = ""
            if include_code:
                source_code = self._get_source_snippet(
                    root_path, node.file_path, node.line, node.end_line
                )

            context_node = ContextNode(
                name=node.name,
                kind=node.kind,
                file_path=node.file_path,
                line=node.line,
                source_code=source_code,
                relevance_score=1.0,
                relationships=["search_match"],
            )
            nodes.append(context_node)

        # Step 2: Find related symbols (callers, callees, same file)
        if len(nodes) < max_nodes:
            for ctx_node in list(nodes):
                if len(nodes) >= max_nodes:
                    break

                # Find node ID
                node_id = self._find_node_id(ctx_node.name, ctx_node.file_path)
                if node_id is None:
                    continue

                # Get callers
                callers = self.call_graph.get_callers(node_id, depth=1)
                for caller in callers[:3]:
                    caller_id = caller.get("id")
                    if caller_id is not None and caller_id in seen_ids:
                        continue
                    if caller_id is not None:
                        seen_ids.add(caller_id)

                    source_code = ""
                    if include_code:
                        caller_file_path = caller.get("file_path", "")
                        caller_line = caller.get("line", 0)
                        caller_end_line = caller.get("end_line", caller_line)
                        source_code = self._get_source_snippet(
                            root_path, caller_file_path, caller_line, caller_end_line
                        )

                    nodes.append(
                        ContextNode(
                            name=caller.get("name", ""),
                            kind=caller.get("kind", ""),
                            file_path=caller.get("file_path", ""),
                            line=caller.get("line", 0),
                            source_code=source_code,
                            relevance_score=0.7,
                            relationships=[f"calls:{ctx_node.name}"],
                        )
                    )

        # Step 3: Sort by relevance and trim
        nodes.sort(key=lambda n: n.relevance_score, reverse=True)
        nodes = nodes[:max_nodes]

        # Estimate tokens (rough approximation: 4 chars ≈ 1 token)
        total_chars = sum(len(n.source_code) + len(n.name) + 50 for n in nodes)
        token_estimate = total_chars // 4

        # Build coverage report
        coverage = {
            "nodes_found": len(search_results),
            "nodes_included": len(nodes),
            "files_covered": len(set(n.file_path for n in nodes)),
            "kinds": list(set(n.kind for n in nodes)),
        }

        return BuiltContext(
            task=task,
            nodes=nodes,
            total_tokens_estimate=token_estimate,
            format=format,
            coverage=coverage,
        )

    def render(self, context: BuiltContext) -> str:
        """Render built context to string."""

        if context.format == "markdown":
            return self._render_markdown(context)
        elif context.format == "json":
            import json

            return json.dumps(
                {
                    "task": context.task,
                    "coverage": context.coverage,
                    "nodes": [
                        {
                            "name": n.name,
                            "kind": n.kind,
                            "file": n.file_path,
                            "line": n.line,
                            "relevance": n.relevance_score,
                            "code": n.source_code,
                        }
                        for n in context.nodes
                    ],
                },
                indent=2,
            )
        else:
            return self._render_markdown(context)

    def _render_markdown(self, context: BuiltContext) -> str:
        """Render as markdown."""

        lines = [
            f"# Context for: {context.task}",
            "",
            f"**Coverage**: {context.coverage['nodes_included']} nodes from "
            f"{context.coverage['files_covered']} files",
            f"**Estimated tokens**: ~{context.total_tokens_estimate}",
            "",
            "---",
            "",
        ]

        for node in context.nodes:
            lines.append(f"## {node.name} ({node.kind})")
            lines.append("")
            lines.append(f"**File**: `{node.file_path}:{node.line}`")
            lines.append(f"**Relevance**: {node.relevance_score:.2f}")
            if node.relationships:
                lines.append(f"**Relationships**: {', '.join(node.relationships)}")
            lines.append("")
            if node.source_code:
                lines.append("```")
                lines.append(node.source_code)
                lines.append("```")
                lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _get_source_snippet(
        self,
        root: Path,
        file_path: str,
        start_line: int,
        end_line: int | None,
        context_lines: int = 3,
    ) -> str:
        """Get source code snippet with context."""

        full_path = root / file_path
        if not full_path.exists():
            return ""

        try:
            lines = full_path.read_text(encoding="utf-8").split("\n")
        except (OSError, UnicodeDecodeError):
            return ""

        start = max(0, start_line - 1 - context_lines)
        end = min(len(lines), (end_line or start_line) + context_lines)

        snippet_lines = []
        for i in range(start, end):
            line_num = i + 1
            prefix = ">>> " if start_line <= line_num <= (end_line or start_line) else "    "
            snippet_lines.append(f"{prefix}{line_num:4d}: {lines[i]}")

        return "\n".join(snippet_lines)

    def _find_node_id(self, name: str, file_path: str) -> int | None:
        """Find node ID by name and file path."""

        results = self.db.search_fts(name, limit=10)
        for result in results:
            if result.get("file_path") == file_path:
                return result.get("id")
        return None

    def close(self) -> None:
        """Close database connections."""

        self.db.close()
