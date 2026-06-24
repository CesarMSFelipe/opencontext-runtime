"""Tests for G2 — honest context pack hash warning (AC-G2-1)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder


def test_build_for_phase_emits_runtime_warning(tmp_path: Path) -> None:
    """AC-G2-1: build_for_phase() emits UserWarning containing 'unavailable'."""
    builder = ContextSubstrateBuilder(root=tmp_path)

    with pytest.warns(UserWarning, match="unavailable"):
        report = builder.build_for_phase(task="test-task", phase="explore", budget=8000)

    assert report is not None


def test_build_for_phase_context_pack_hash_is_none(tmp_path: Path) -> None:
    """AC-G2-1: returned substrate has context_pack_hash=None (no fake hash)."""
    builder = ContextSubstrateBuilder(root=tmp_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        report = builder.build_for_phase(task="test-task", phase="explore", budget=8000)

    assert report.context_pack_hash is None


def test_build_for_phase_used_tokens_is_zero(tmp_path: Path) -> None:
    """G2: used_tokens must be 0 when no real pack is built — not a fake estimate."""
    builder = ContextSubstrateBuilder(root=tmp_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        report = builder.build_for_phase(task="test-task", phase="apply", budget=4000)

    assert report.used_tokens == 0
    assert report.available_tokens == 4000
