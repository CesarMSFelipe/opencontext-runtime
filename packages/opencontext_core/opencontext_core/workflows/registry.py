"""Workflow registry and YAML loader (spec WR1, SDD1, YAML1).

The registry holds validated :class:`WorkflowDefinition` objects and is the single
lookup surface for resolution. Registering a new (e.g. OC Flow) definition requires
no Runtime Core change — only ``register()`` (spec WR1). Built-in workflows are
loaded from validated YAML templates under ``builtins/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from opencontext_core.workflows.builtins import builtins_dir
from opencontext_core.workflows.definition import (
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
)
from opencontext_core.workflows.validation import (
    CoexistenceReport,
    WorkflowValidationError,
    ensure_unique_node_ids,
    validate,
    validate_coexistence,
)


class WorkflowNotFound(KeyError):
    """Raised when a workflow id is not registered (spec WR1)."""


# The registry exposes a ``list()`` method (spec WR1), which shadows the builtin
# ``list`` inside the class scope where return annotations are resolved. These
# module-level aliases capture the builtin generic so the annotations stay correct.
_DefinitionList = list[WorkflowDefinition]
_IdList = list[str]


def load_definition_from_yaml(path: str | Path) -> WorkflowDefinition:
    """Parse and validate a workflow definition from a YAML template (spec YAML1).

    Nodes are authored as a list (ordered, human-readable); duplicate node ids are
    rejected here before the list is collapsed into the keyed ``nodes`` map.
    """
    raw_text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text)
    if not isinstance(data, dict):
        raise WorkflowValidationError(f"workflow template {path} is not a mapping")
    return definition_from_dict(data)


def definition_from_dict(data: dict[str, Any]) -> WorkflowDefinition:
    """Build and validate a :class:`WorkflowDefinition` from a raw mapping."""
    node_list = data.get("nodes", [])
    if not isinstance(node_list, list):
        raise WorkflowValidationError("'nodes' must be a list in a workflow template")

    node_ids = [n.get("id") for n in node_list if isinstance(n, dict)]
    ensure_unique_node_ids([nid for nid in node_ids if isinstance(nid, str)])

    nodes: dict[str, WorkflowNodeDefinition] = {}
    for node in node_list:
        parsed = WorkflowNodeDefinition.model_validate(node)
        nodes[parsed.id] = parsed

    edges = [WorkflowEdgeDefinition.model_validate(e) for e in data.get("edges", [])]

    payload = {k: v for k, v in data.items() if k not in ("nodes", "edges")}
    payload["nodes"] = nodes
    payload["edges"] = edges
    defn = WorkflowDefinition.model_validate(payload)
    validate(defn)
    return defn


class WorkflowRegistry:
    """Registers, retrieves, lists, describes, and validates workflow definitions."""

    def __init__(self) -> None:
        self._defs: dict[str, WorkflowDefinition] = {}

    @classmethod
    def with_builtins(cls) -> WorkflowRegistry:
        """Construct a registry pre-loaded with the built-in workflows."""
        registry = cls()
        registry._load_builtins()
        return registry

    def register(self, definition: WorkflowDefinition) -> None:
        """Validate then store ``definition`` keyed by its id (spec WR1)."""
        validate(definition)
        self._defs[definition.id] = definition

    def get(self, workflow_id: str) -> WorkflowDefinition:
        """Return the definition for ``workflow_id``; raise if unknown (spec WR1)."""
        try:
            return self._defs[workflow_id]
        except KeyError as exc:
            raise WorkflowNotFound(f"unknown workflow: {workflow_id!r}") from exc

    def has(self, workflow_id: str) -> bool:
        """Return True when ``workflow_id`` is registered."""
        return workflow_id in self._defs

    def list(self) -> _DefinitionList:
        """Return all registered definitions (spec WR1)."""
        return list(self._defs.values())

    def list_ids(self) -> _IdList:
        """Return all registered workflow ids."""
        return list(self._defs.keys())

    def describe(self, workflow_id: str) -> dict[str, Any]:
        """Return an inspectable summary of a workflow (spec WR1, feeds explain)."""
        defn = self.get(workflow_id)
        return {
            "id": defn.id,
            "uid": defn.uid,
            "label": defn.label,
            "kind": defn.kind,
            "version": defn.version,
            "schema_version": defn.schema_version,
            "strategy": str(defn.strategy),
            "expected_cost": str(defn.expected_cost),
            "risk_level": str(defn.risk_level),
            "default_profile": defn.default_profile,
            "compatible_profiles": list(defn.compatible_profiles),
            "required_capabilities": list(defn.required_capabilities),
            "profiles": {name: list(ids) for name, ids in defn.profiles.items()},
            "nodes": list(defn.nodes.keys()),
            "start_node": defn.start_node,
            "terminal_nodes": list(defn.terminal_nodes),
        }

    def validate_coexistence(self) -> CoexistenceReport:
        """Assert all registered kinds coexist over shared infra (WR-CONV)."""
        return validate_coexistence(self.list())

    def _load_builtins(self) -> None:
        """Load and register every built-in workflow under ``builtins/``.

        Registers the declarative SDD definition (``sdd.yaml``) and the derived
        ``sdd-quality`` definition that backs the legacy ``full+judgment`` /
        ``full+gga`` / ``full+quality`` tracks (built from the SDD graph so it never
        drifts). The alias table maps every legacy track name onto one of these, so
        registry resolution succeeds for all known legacy tracks and
        ``workflow.validation.failed`` is reserved for genuinely unknown workflows.
        """
        from opencontext_core.workflows.builtins.legacy import build_sdd_quality

        sdd_path = builtins_dir() / "sdd.yaml"
        if sdd_path.exists():
            sdd = load_definition_from_yaml(sdd_path)
            self.register(sdd)
            self.register(build_sdd_quality(sdd))
