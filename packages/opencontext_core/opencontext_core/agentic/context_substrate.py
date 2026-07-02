"""ContextSubstrateReport — thin adapter over ContextPackBuilder for per-phase context stats.

Produces a Pydantic summary of what was packed, compressed, and omitted for a given
task and phase. The ContextSubstrateBuilder is stateless; call build_for_phase() freely.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from opencontext_core.config import load_config_or_defaults
from opencontext_core.config_resolver import (
    resolve_active_storage_path,
    resolve_active_workspace_path,
    resolve_config_path,
)


class ContextSubstrateReport(BaseModel, extra="forbid"):
    """Summary of the context substrate built for one conductor phase."""

    schema_version: str = "opencontext.context_substrate.v1"
    indexed: bool
    graph_status: str
    context_pack_hash: str | None = None
    no_kg_reason: str | None = None
    used_tokens: int = 0
    available_tokens: int = 0
    compression_enabled: bool = False
    compression_savings: int = 0
    omissions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # NOTE: Token measurement fields — populated when KG content is available.
    baseline_tokens: int = 0
    selected_tokens: int = 0
    compressed_tokens: int = 0


class ContextSubstrateBuilder:
    """Builds a ContextSubstrateReport for a task/phase without side effects."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)

    def build_for_phase(
        self,
        *,
        task: str,
        phase: str,
        budget: int | None,
        include_memory: bool = True,
    ) -> ContextSubstrateReport:
        """Return a ContextSubstrateReport summarising available context for *phase*.

        NOTE: G2 — ContextPackBuilder and CompressionEngine are not available.
        Emits a RuntimeWarning and sets context_pack_hash=None (honest, no fake hash).
        """
        indexed, graph_status = self._check_index()
        available = budget or 0
        substrate_warnings: list[str] = []
        context_pack_hash: str | None = None
        no_kg_reason: str | None = None

        sqlite_tokens: int = 0
        if not indexed:
            substrate_warnings.append(
                f"Knowledge graph not indexed — context for {phase!r} may be limited."
            )
            no_kg_reason = "knowledge_graph.json not found"
        else:
            kg_file = resolve_active_workspace_path(self.root) / "knowledge_graph.json"
            if kg_file.exists():
                try:
                    kg_data = json.loads(kg_file.read_text(encoding="utf-8"))
                    # Collect sortable identifiers from the KG.
                    if isinstance(kg_data, dict) and "nodes" in kg_data:
                        nodes = kg_data["nodes"]
                        if isinstance(nodes, list):
                            keys = sorted(
                                str(n.get("id", n.get("path", "")))
                                for n in nodes
                                if isinstance(n, dict)
                            )
                        else:
                            keys = sorted(str(k) for k in nodes)
                    elif isinstance(kg_data, dict):
                        keys = sorted(kg_data.keys())
                    elif isinstance(kg_data, list):
                        keys = sorted(
                            str(n.get("id", n.get("path", ""))) if isinstance(n, dict) else str(n)
                            for n in kg_data
                        )
                    else:
                        keys = [str(kg_data)]
                    digest = hashlib.sha256("\n".join(keys).encode()).hexdigest()
                    context_pack_hash = f"sha256:{digest}"
                except Exception as exc:
                    substrate_warnings.append(f"Failed to hash knowledge graph: {exc}")
                    no_kg_reason = f"knowledge_graph.json unreadable: {exc}"
                    context_pack_hash = None
            else:
                # NOTE: SQLite index present but no JSON KG — derive hash + tokens
                # from the GraphDatabase nodes table using the same reader as graph.py.
                sqlite_db = resolve_active_storage_path(self.root) / "context_graph.db"
                try:
                    from opencontext_core.indexing.graph_db import GraphDatabase

                    # NOTE: Keep db reference alive so _conn is not GC-closed.
                    db = GraphDatabase(sqlite_db)
                    conn = db._connect()
                    rows = conn.execute("SELECT id, content_snippet FROM nodes").fetchall()
                    sorted_ids = sorted(str(r["id"]) for r in rows)
                    joined_content = " ".join(
                        str(r["content_snippet"] or "") for r in rows if r["content_snippet"]
                    )
                    digest = hashlib.sha256("\n".join(sorted_ids).encode()).hexdigest()
                    context_pack_hash = f"sha256:{digest}"
                    # NOTE: used_tokens estimated from word count x 1.3 token factor.
                    sqlite_tokens = int(len(joined_content.split()) * 1.3)
                except Exception as exc:
                    substrate_warnings.append(f"Failed to read SQLite graph: {exc}")
                    context_pack_hash = None
                    sqlite_tokens = 0

        baseline_tokens = 0
        selected_tokens = 0
        compressed_tokens = 0
        raw_kg_content: str = ""
        if context_pack_hash is not None:
            if sqlite_tokens:
                selected_tokens = sqlite_tokens
            else:
                try:
                    raw_kg_content = (
                        resolve_active_workspace_path(self.root)
                        / "knowledge_graph.json"
                    ).read_text(encoding="utf-8")
                    selected_tokens = int(len(raw_kg_content.split()) * 1.3)
                except Exception:
                    selected_tokens = 0
            baseline_tokens = selected_tokens
            compressed_tokens = selected_tokens

        # G2: wire CompressionEngine when KG content is available.
        # Use compress_item() directly to measure compression savings on the full
        # KG payload regardless of budget.  pack() is budget-management; here we
        # want raw stats: "how much would the engine shrink this content?".
        #
        # NOTE (SUGGESTION-6): SQLite/JSON asymmetry — when the project uses a
        # SQLite-backed KG (no knowledge_graph.json), raw_kg_content is empty.
        # Compressing the synthetic {"note": "sqlite-backed kg"} placeholder
        # would produce baseline/compressed counts (char-based estimate_tokens)
        # that are inconsistent with selected_tokens (word-count × 1.3 from
        # real SQLite content), breaking the invariant selected_tokens >= used_tokens.
        # For the SQLite path we skip CompressionEngine entirely — all token fields
        # remain anchored to the same sqlite_tokens estimate so the report is honest.
        compression_enabled = False
        compression_savings = 0
        if context_pack_hash is not None and selected_tokens > 0 and raw_kg_content:
            try:
                from opencontext_core.context.budgeting import estimate_tokens
                from opencontext_core.context.compression import CompressionEngine
                from opencontext_core.models.context import (
                    ContextItem,
                    ContextPriority,
                )

                cfg = load_config_or_defaults(
                    resolve_config_path(self.root), auto_detect=False
                )
                engine = CompressionEngine(cfg.context.compression)

                # Build a single ContextItem representing the KG text payload.
                # Use estimate_tokens (char-based) for consistency with the engine.
                kg_token_count = estimate_tokens(raw_kg_content)
                kg_item = ContextItem(
                    id="kg:context_substrate",
                    content=raw_kg_content,
                    source="knowledge_graph",
                    source_type="file",
                    priority=ContextPriority.P1,
                    tokens=kg_token_count,
                    score=1.0,
                )
                result = engine.compress_item(kg_item)
                compressed_tokens = result.compressed_tokens
                baseline_tokens = result.original_tokens
                compression_savings = max(0, baseline_tokens - compressed_tokens)
                compression_enabled = True
            except Exception as exc:
                substrate_warnings.append(
                    f"CompressionEngine wiring skipped: {exc}"
                )

        used_tokens = compressed_tokens

        report = ContextSubstrateReport(
            indexed=indexed,
            graph_status=graph_status,
            context_pack_hash=context_pack_hash,
            no_kg_reason=no_kg_reason,
            used_tokens=used_tokens,
            available_tokens=available,
            compression_enabled=compression_enabled,
            compression_savings=compression_savings,
            omissions=[],
            warnings=substrate_warnings,
            baseline_tokens=baseline_tokens,
            selected_tokens=selected_tokens,
            compressed_tokens=compressed_tokens,
        )

        # S2: persist the report so sync_state() can read the latest hash cheaply.
        try:
            storage_dir = resolve_active_storage_path(self.root)
            storage_dir.mkdir(parents=True, exist_ok=True)
            report_path = storage_dir / "substrate_report.json"
            report_path.write_text(
                json.dumps(report.model_dump(), indent=2), encoding="utf-8"
            )
        except Exception:
            pass  # Persist is best-effort; never fail build_for_phase.

        return report

    def _check_index(self) -> tuple[bool, str]:
        """Return (is_indexed, status_message) by probing the .opencontext directory.

        Checks both the legacy knowledge_graph.json and the SQLite context graph DB
        that the current indexer writes to .storage/opencontext/context_graph.db.
        """
        # Primary: SQLite KG written by the current indexer.
        sqlite_db = resolve_active_storage_path(self.root) / "context_graph.db"
        if sqlite_db.exists():
            return True, "indexed"
        # Fallback: legacy JSON snapshot.
        oc_dir = resolve_active_workspace_path(self.root)
        if not oc_dir.exists():
            return False, "not_indexed"
        kg_file = oc_dir / "knowledge_graph.json"
        if kg_file.exists():
            return True, "indexed"
        return False, "directory_exists_no_graph"


if __name__ == "__main__":
    import json as _json
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        builder = ContextSubstrateBuilder(root=tmp)
        # Case 1: no KG — hash is None, no_kg_reason is set.
        report = builder.build_for_phase(task="add health check", phase="explore", budget=8000)
        assert isinstance(report, ContextSubstrateReport)
        assert report.available_tokens == 8000
        assert report.context_pack_hash is None, f"Expected None, got {report.context_pack_hash}"
        assert report.no_kg_reason is not None

        # Case 2: KG present — hash is deterministic.
        import os

        oc_dir = os.path.join(tmp, ".opencontext")
        os.makedirs(oc_dir, exist_ok=True)
        kg_path = os.path.join(oc_dir, "knowledge_graph.json")
        kg_content = {"nodes": [{"id": "a"}, {"id": "b"}]}
        with open(kg_path, "w") as fh:
            _json.dump(kg_content, fh)
        report2 = builder.build_for_phase(task="add health check", phase="explore", budget=8000)
        assert report2.context_pack_hash is not None
        assert report2.context_pack_hash.startswith("sha256:")
        assert report2.indexed is True
        # Determinism: same KG → same hash.
        report3 = builder.build_for_phase(task="other", phase="design", budget=4000)
        assert report2.context_pack_hash == report3.context_pack_hash

        # Round-trip
        ContextSubstrateReport.model_validate(report2.model_dump())

    print("agentic/context_substrate.py self-check passed.")
