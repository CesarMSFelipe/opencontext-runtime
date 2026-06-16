"""Configurable rules engine: unified discovery, layering, and injection.

This package consolidates the two historically overlapping convention parsers
(``opencontext_core.dx.agent_hints.AgentHintsManager`` and
``opencontext_core.dx.instructions.import_instructions``) behind a single
discovery + resolution entry point. It reuses the existing parse logic rather
than introducing a third parser, resolves layered precedence
(global < project < change), records overrides, and converts each resolved rule
into a trust-tagged ``EvidenceItem`` so rules flow through the verified-context
spine and the context firewall like any other evidence.
"""

from __future__ import annotations

from opencontext_core.rules.loader import (
    ResolvedRule,
    ResolvedRules,
    RulesConfig,
    RulesLoader,
    SkippedRule,
)

__all__ = [
    "ResolvedRule",
    "ResolvedRules",
    "RulesConfig",
    "RulesLoader",
    "SkippedRule",
]
