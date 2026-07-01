"""opencontext_sdd — Spec-Driven Development status resolver and dispatcher.

Public surface (per ``openspec/changes/agentic-parity-engram-gentle/design.md``
§Public Python API):

* ``Status`` / ``Resolve`` / ``parse_verify_report`` — conductor artifacts.
* ``RenderDispatcherMarkdown`` / ``RenderNativePhasePrompt`` — native prompts.
* ``refresh_skill_registry`` / ``get_skill_paths`` — skill-registry producer.
* ``Catalog`` — skills + agents + triggers single source of truth.
"""

from __future__ import annotations

from opencontext_sdd.catalog import Catalog
from opencontext_sdd.dispatcher import (
    RenderDispatcherMarkdown,
    RenderNativePhasePrompt,
)
from opencontext_sdd.skill_registry import (
    get_skill_paths,
    refresh_skill_registry,
)
from opencontext_sdd.status import (
    Resolve,
    Status,
    parse_verify_report,
)

__all__ = [
    "Catalog",
    "RenderDispatcherMarkdown",
    "RenderNativePhasePrompt",
    "Resolve",
    "Status",
    "get_skill_paths",
    "parse_verify_report",
    "refresh_skill_registry",
]
