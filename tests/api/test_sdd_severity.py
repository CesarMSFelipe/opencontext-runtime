"""REQ-04a: POST /v1/refactor/sdd returns 200 and severity derived from findings.

Verifies that `scan.severity.value` is no longer accessed (which would raise
AttributeError), and that severity is "high" when findings exist and "none"
when they don't.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_scan(findings: list[str]):
    from opencontext_core.dx.security_reports import SecurityScanResult

    return SecurityScanResult(findings=findings, warnings=[], files_scanned=0)


def test_sdd_endpoint_returns_200_with_findings(tmp_path: Path) -> None:
    """POST /v1/refactor/sdd returns 200; severity == 'high' when findings present."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import opencontext_api.main as api_main

    scan_with_findings = _make_scan(["possible-secret-leaked"])

    with patch.object(api_main, "scan_project", return_value=scan_with_findings):
        # Patch runtime to avoid real index
        fake_prepared = MagicMock()
        fake_prepared.query = "test query"
        fake_prepared.context = "ctx"
        fake_prepared.included_sources = []
        fake_prepared.omitted_sources = []
        fake_prepared.token_usage = 0
        fake_prepared.trust_decision = "trusted"
        fake_prepared.fallback_actions = []
        fake_prepared.source_surfaces = []
        fake_prepared.trace_id = "trace-123"

        fake_runtime = MagicMock()
        fake_runtime.prepare_context.return_value = fake_prepared
        fake_runtime.config = MagicMock()
        fake_runtime.load_manifest.return_value = MagicMock(files=[])

        fake_firewall = MagicMock()
        fake_firewall.check_context_export.return_value = MagicMock(allowed=True, reason="ok")

        with patch.object(api_main, "_runtime", return_value=fake_runtime):
            with patch("opencontext_core.safety.firewall.ContextFirewall", return_value=fake_firewall):
                client = TestClient(api_main.app)
                resp = client.post(
                    "/v1/refactor/sdd",
                    json={"query": "test", "root": str(tmp_path), "refresh_index": False},
                )

    assert resp.status_code == 200
    safety = resp.json()["result"]["safety"]
    assert safety["security_scan_severity"] == "high"
    assert safety["security_findings"] == 1


def test_sdd_endpoint_returns_200_without_findings(tmp_path: Path) -> None:
    """POST /v1/refactor/sdd returns 200; severity == 'none' when no findings."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import opencontext_api.main as api_main

    scan_no_findings = _make_scan([])

    with patch.object(api_main, "scan_project", return_value=scan_no_findings):
        fake_prepared = MagicMock()
        fake_prepared.query = "test query"
        fake_prepared.context = "ctx"
        fake_prepared.included_sources = []
        fake_prepared.omitted_sources = []
        fake_prepared.token_usage = 0
        fake_prepared.trust_decision = "trusted"
        fake_prepared.fallback_actions = []
        fake_prepared.source_surfaces = []
        fake_prepared.trace_id = "trace-456"

        fake_runtime = MagicMock()
        fake_runtime.prepare_context.return_value = fake_prepared
        fake_runtime.config = MagicMock()
        fake_runtime.load_manifest.return_value = MagicMock(files=[])

        fake_firewall = MagicMock()
        fake_firewall.check_context_export.return_value = MagicMock(allowed=True, reason="ok")

        with patch.object(api_main, "_runtime", return_value=fake_runtime):
            with patch("opencontext_core.safety.firewall.ContextFirewall", return_value=fake_firewall):
                client = TestClient(api_main.app)
                resp = client.post(
                    "/v1/refactor/sdd",
                    json={"query": "test", "root": str(tmp_path), "refresh_index": False},
                )

    assert resp.status_code == 200
    safety = resp.json()["result"]["safety"]
    assert safety["security_scan_severity"] == "none"
    assert safety["security_findings"] == 0
