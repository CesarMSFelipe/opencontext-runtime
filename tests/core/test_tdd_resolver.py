"""TDDPolicyResolver — maps OpenSpecConfig.tdd.mode to a TDDPolicy.

Three levels: strict (RED-first enforced), lite (test required, not RED-first),
off (advisory only).
"""

from __future__ import annotations

from opencontext_core.openspec.config import OpenSpecConfig, TDDSection
from opencontext_core.tdd.policy import TDDPolicy, TDDPolicyResolver


def test_resolve_strict() -> None:
    cfg = OpenSpecConfig(tdd=TDDSection(mode="strict"))
    assert TDDPolicyResolver().resolve(cfg) == TDDPolicy.STRICT


def test_resolve_lite() -> None:
    cfg = OpenSpecConfig(tdd=TDDSection(mode="lite"))
    assert TDDPolicyResolver().resolve(cfg) == TDDPolicy.LITE


def test_resolve_off() -> None:
    cfg = OpenSpecConfig(tdd=TDDSection(mode="off"))
    assert TDDPolicyResolver().resolve(cfg) == TDDPolicy.OFF


def test_resolve_default_is_strict() -> None:
    """Default config (no explicit tdd block) maps to strict."""
    cfg = OpenSpecConfig()
    assert TDDPolicyResolver().resolve(cfg) == TDDPolicy.STRICT
