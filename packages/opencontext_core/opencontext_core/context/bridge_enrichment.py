"""Bridge enrichment — annotate context packs with cross-language bridge data."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def enrich_with_bridges(pack: Any, root: str | Path = ".") -> Any:
    """Annotate a context pack with cross-language bridge data.

    Scans the project for bridges and appends the results to pack.metadata["bridges"].
    Returns the pack unchanged (no bridges key) if none are detected.

    Args:
        pack: A ContextPackResult or any object with a mutable `metadata` dict.
        root: Project root directory to scan.

    Returns:
        The pack with metadata["bridges"] populated if bridges were found.
    """
    from opencontext_core.indexing.bridge_detector import BridgeDetector

    detector = BridgeDetector()
    bridges = detector.scan(root)

    if not bridges:
        return pack

    pack.metadata["bridges"] = [
        {
            "source_file": b.source_file,
            "source_symbol": b.source_symbol,
            "target_hint": b.target_hint,
            "bridge_type": b.bridge_type,
            "confidence": round(b.confidence, 2),
            "line": b.line,
        }
        for b in bridges
    ]
    return pack
