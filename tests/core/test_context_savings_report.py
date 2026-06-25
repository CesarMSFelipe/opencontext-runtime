"""Tests for ContextSavingsReport (slice 4: context economy).

The report MUST degrade gracefully when ContextPackBuilder is unavailable —
returning ``degraded=True`` with a labelled warning rather than raising.
We never fabricate savings metrics when no real packer ran.
"""

from __future__ import annotations

from opencontext_core.context.savings import ContextSavingsReport


def test_build_degrades_when_pack_builder_absent(monkeypatch) -> None:
    # Simulate ContextPackBuilder being unavailable by removing it from the
    # packing module the report looks at during build().
    import opencontext_core.context.packing as packing_mod

    monkeypatch.setattr(packing_mod, "ContextPackBuilder", None, raising=False)

    report = ContextSavingsReport.build()
    assert report.degraded is True
    assert isinstance(report.warning, str) and report.warning
    assert report.tokens_saved == 0
    assert report.tokens_without_pack == 0


def test_build_does_not_raise_when_packing_module_unavailable(monkeypatch) -> None:
    """Even if the entire packing module disappears, build() returns cleanly."""

    # Replace the module reference inside savings so ``import`` raises.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opencontext_core.context.packing":
            raise ImportError("simulated: ContextPackBuilder not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    # Must not raise; must return a degraded report.
    report = ContextSavingsReport.build()
    assert report.degraded is True
    assert report.warning


def test_report_shape_exposes_required_fields() -> None:
    report = ContextSavingsReport.build()
    for field_name in ("degraded", "warning", "tokens_saved", "tokens_without_pack"):
        assert hasattr(report, field_name)
