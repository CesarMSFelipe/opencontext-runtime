"""Tests for cross-language bridge detection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opencontext_core.indexing.bridge_detector import BridgeDetector, CrossLanguageBridge


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write(tmp_path: Path, filename: str, content: str) -> Path:
    f = tmp_path / filename
    f.write_text(content, encoding="utf-8")
    return f


# ── CrossLanguageBridge dataclass ────────────────────────────────────────────


def test_bridge_dataclass_fields() -> None:
    """CrossLanguageBridge has the expected fields."""
    b = CrossLanguageBridge(
        source_file="src/client.py",
        source_symbol="fetch_data",
        target_hint="requests.get(",
        bridge_type="HTTP",
        confidence=0.9,
        line=12,
    )
    assert b.source_file == "src/client.py"
    assert b.bridge_type == "HTTP"
    assert b.confidence == 0.9
    assert b.line == 12


# ── HTTP detection ───────────────────────────────────────────────────────────


def test_detect_http_requests_import(tmp_path: Path) -> None:
    """Python file importing 'requests' triggers HTTP bridge."""
    _write(tmp_path, "client.py", "import requests\nresponse = requests.get('http://api')\n")
    bridges = BridgeDetector().scan(tmp_path)
    assert any(b.bridge_type == "HTTP" for b in bridges)


def test_detect_http_httpx(tmp_path: Path) -> None:
    """httpx usage triggers HTTP bridge."""
    _write(tmp_path, "api.py", "import httpx\nclient = httpx.Client()\n")
    bridges = BridgeDetector().scan(tmp_path)
    assert any(b.bridge_type == "HTTP" for b in bridges)


def test_detect_http_go_client(tmp_path: Path) -> None:
    """Go http.Get() triggers HTTP bridge."""
    _write(tmp_path, "main.go", 'resp, err := http.Get("http://example.com")\n')
    bridges = BridgeDetector().scan(tmp_path)
    assert any(b.bridge_type == "HTTP" for b in bridges)


# ── gRPC detection ───────────────────────────────────────────────────────────


def test_detect_grpc_pb2(tmp_path: Path) -> None:
    """Import of _pb2_grpc triggers GRPC bridge."""
    _write(tmp_path, "service.py", "import my_service_pb2_grpc as stub\n")
    bridges = BridgeDetector().scan(tmp_path)
    assert any(b.bridge_type == "GRPC" for b in bridges)


def test_detect_grpc_channel(tmp_path: Path) -> None:
    """grpc.insecure_channel() triggers GRPC bridge."""
    _write(tmp_path, "client.py", "channel = grpc.insecure_channel('localhost:50051')\n")
    bridges = BridgeDetector().scan(tmp_path)
    assert any(b.bridge_type == "GRPC" for b in bridges)


# ── CLI subprocess detection ─────────────────────────────────────────────────


def test_detect_subprocess_run(tmp_path: Path) -> None:
    """subprocess.run() with a list triggers CLI_SUBPROCESS bridge."""
    _write(tmp_path, "runner.py", 'import subprocess\nsubprocess.run(["node", "script.js"])\n')
    bridges = BridgeDetector().scan(tmp_path)
    assert any(b.bridge_type == "CLI_SUBPROCESS" for b in bridges)


def test_detect_node_child_process(tmp_path: Path) -> None:
    """child_process.exec() triggers CLI_SUBPROCESS bridge."""
    _write(tmp_path, "runner.ts", "const cp = child_process.exec('python main.py');\n")
    bridges = BridgeDetector().scan(tmp_path)
    assert any(b.bridge_type == "CLI_SUBPROCESS" for b in bridges)


# ── No bridges ────────────────────────────────────────────────────────────────


def test_empty_project_returns_no_bridges(tmp_path: Path) -> None:
    """Pure Python project with no bridge patterns returns empty list."""
    _write(tmp_path, "pure.py", "def add(a, b):\n    return a + b\n\nresult = add(1, 2)\n")
    bridges = BridgeDetector().scan(tmp_path)
    assert bridges == []


def test_no_bridges_in_empty_directory(tmp_path: Path) -> None:
    """Empty directory returns no bridges."""
    bridges = BridgeDetector().scan(tmp_path)
    assert bridges == []


# ── Confidence and sorting ────────────────────────────────────────────────────


def test_bridges_sorted_by_confidence_descending(tmp_path: Path) -> None:
    """Bridges are returned sorted by confidence, highest first."""
    _write(
        tmp_path,
        "mixed.py",
        "import requests\nos.popen('node script')\nsubprocess.run(['go', 'run', '.'])\n",
    )
    bridges = BridgeDetector().scan(tmp_path)
    if len(bridges) >= 2:
        for i in range(len(bridges) - 1):
            assert bridges[i].confidence >= bridges[i + 1].confidence


# ── Bridge enrichment ─────────────────────────────────────────────────────────


def test_enrich_with_bridges_adds_metadata(tmp_path: Path) -> None:
    """enrich_with_bridges() adds bridge data to pack metadata."""
    from opencontext_core.context.bridge_enrichment import enrich_with_bridges

    _write(tmp_path, "client.py", "import requests\nresponse = requests.get('http://api')\n")

    pack = SimpleNamespace(metadata={})
    result = enrich_with_bridges(pack, root=tmp_path)

    assert "bridges" in result.metadata
    assert len(result.metadata["bridges"]) >= 1
    assert result.metadata["bridges"][0]["bridge_type"] == "HTTP"


def test_enrich_no_bridges_unchanged(tmp_path: Path) -> None:
    """enrich_with_bridges() leaves pack unchanged when no bridges found."""
    from opencontext_core.context.bridge_enrichment import enrich_with_bridges

    _write(tmp_path, "pure.py", "x = 1\n")
    pack = SimpleNamespace(metadata={})
    result = enrich_with_bridges(pack, root=tmp_path)
    assert "bridges" not in result.metadata
