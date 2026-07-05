"""PersonaRegistry — registry-driven persona resolution (PR-006, book doc 05 §4).

Seeds the built-in :class:`PersonaDefinition`s from the legacy ``Persona`` tuple
(the prompt/tools/visibility source) merged with the governance enrichment in
``builtins/core.yaml``. Registering a new persona requires no Runtime change — only
``register()`` (book §17). When ``runtime.persona_registry_enabled`` is off, callers
keep using the legacy ``get_persona``/``PHASE_PERSONAS`` path unchanged.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Any

import yaml

from opencontext_core.personas.definition import PersonaDefinition
from opencontext_core.registries.base import Registry, RegistryNotFound

__all__ = ["PersonaNotFound", "PersonaRegistry", "builtins_dir"]


class PersonaNotFound(RegistryNotFound):
    """Raised when a persona id is not registered."""


def builtins_dir() -> Any:
    """Directory holding the built-in persona enrichment YAML."""
    return files(__package__) / "builtins"


def _load_enrichment() -> dict[str, dict[str, Any]]:
    """Load the persona enrichment table keyed by persona id."""
    path = builtins_dir() / "core.yaml"
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    table: dict[str, dict[str, Any]] = {}
    for entry in raw:
        if isinstance(entry, dict) and entry.get("id"):
            table[str(entry["id"])] = {k: v for k, v in entry.items() if k != "id"}
    return table


class PersonaRegistry(Registry[PersonaDefinition]):
    """Registers, retrieves, and lists persona definitions."""

    kind = "persona"

    def get(self, definition_id: str) -> PersonaDefinition:
        try:
            return super().get(definition_id)
        except RegistryNotFound as exc:
            raise PersonaNotFound(str(exc)) from exc

    @classmethod
    def with_builtins(cls) -> PersonaRegistry:
        """Construct a registry seeded with every built-in persona definition."""
        from opencontext_core.personas import PERSONAS

        registry = cls()
        enrichment = _load_enrichment()
        for persona in PERSONAS:
            defn = PersonaDefinition.from_legacy(persona, **enrichment.get(persona.id, {}))
            registry.register(defn)
        return registry
