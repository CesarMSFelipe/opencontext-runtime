"""REQ-plugin-v1-004: ConformanceSuite categories + built-in passes."""

from __future__ import annotations

from opencontext_core.plugins.v2.conformance import (
    ConformanceReport,
    ConformanceSuite,
)
from opencontext_core.plugins.v2.manifest import PluginManifest


def test_REQ_plugin_v1_004_five_categories() -> None:
    suite = ConformanceSuite()
    assert len(suite.categories) == 5


def test_REQ_plugin_v1_004_builtin_passes() -> None:
    suite = ConformanceSuite()
    manifest = PluginManifest(plugin_id="demo", version="1.0.0")
    report = suite.run(manifest)
    assert isinstance(report, ConformanceReport)
    assert report.passed is True


def test_invalid_manifest_blocks() -> None:
    suite = ConformanceSuite()
    report = suite.run(None)
    assert report.passed is False