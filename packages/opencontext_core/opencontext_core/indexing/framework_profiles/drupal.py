"""Drupal convention extraction (PR-008, KG-13; OC-KG-001 §15).

Extracts routes (``*.routing.yml``), services (``*.services.yml``), permissions
(``*.permissions.yml``), and PHPUnit tests into typed KG v2 nodes/edges with
evidence. Detection is by Drupal markers (``*.info.yml`` with a Drupal core
requirement, or a ``*.routing.yml`` next to a ``Drupal\\`` namespace); absent
markers => empty extraction.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from opencontext_core.indexing.framework_profiles.base import (
    FrameworkExtraction,
    evidence_for,
    load_yaml,
    rel,
)
from opencontext_core.indexing.graph_db import is_test_path
from opencontext_core.models.kg_v2 import (
    KgEdge,
    KgEdgeType,
    KgNode,
    KgNodeType,
    kg_edge_id,
    kg_node_id,
)

_SKIP_DIRS = frozenset({".git", "vendor", "node_modules", "__pycache__"})


class DrupalProfile:
    """Extractor for Drupal projects."""

    name = "drupal"

    def detect(self, root: Path) -> bool:
        """True when a Drupal ``*.info.yml`` or ``*.routing.yml`` marker is present."""
        for info in _iter(root, "*.info.yml"):
            data = load_yaml(info)
            is_drupal = "core_version_requirement" in data or data.get("type") in {
                "module",
                "theme",
                "profile",
            }
            if is_drupal:
                return True
        return any(True for _ in _iter(root, "*.routing.yml"))

    def extract(self, root: Path) -> FrameworkExtraction:
        out = FrameworkExtraction()
        for routing in _iter(root, "*.routing.yml"):
            _extract_routes(root, routing, out)
        for services in _iter(root, "*.services.yml"):
            _extract_services(root, services, out)
        for perms in _iter(root, "*.permissions.yml"):
            _extract_config(root, perms, out, kind="permissions")
        for test in _iter(root, "*Test.php"):
            _extract_test(root, test, out)
        return out


def _iter(root: Path, pattern: str) -> Iterator[Path]:
    for path in root.rglob(pattern):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _extract_routes(root: Path, path: Path, out: FrameworkExtraction) -> None:
    rel_path = rel(root, path)
    data = load_yaml(path)
    for route_name, spec in data.items():
        if not isinstance(spec, dict):
            continue
        route_id = kg_node_id("route", route_name, rel_path)
        out.nodes.append(
            KgNode(
                id=route_id,
                type=KgNodeType.ROUTE,
                name=route_name,
                path=rel_path,
                properties={"path": spec.get("path", "")},
                evidence=[evidence_for(rel_path)],
            )
        )
        handler = _route_handler(spec)
        if handler:
            handler_id = kg_node_id("method", handler)
            out.nodes.append(
                KgNode(
                    id=handler_id,
                    type=KgNodeType.METHOD,
                    name=handler,
                    path=rel_path,
                    evidence=[evidence_for(rel_path)],
                )
            )
            out.edges.append(
                KgEdge(
                    id=kg_edge_id(route_id, handler_id, KgEdgeType.ROUTES_TO.value),
                    source_id=route_id,
                    target_id=handler_id,
                    type=KgEdgeType.ROUTES_TO,
                    evidence=[evidence_for(rel_path)],
                )
            )


def _route_handler(spec: dict[str, Any]) -> str:
    defaults = spec.get("defaults", {})
    if isinstance(defaults, dict):
        for key in ("_controller", "_form", "_entity_form"):
            value = defaults.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _extract_services(root: Path, path: Path, out: FrameworkExtraction) -> None:
    rel_path = rel(root, path)
    data = load_yaml(path)
    services = data.get("services", {})
    if not isinstance(services, dict):
        return
    for service_name, spec in services.items():
        if not isinstance(service_name, str):
            continue
        cls = spec.get("class") if isinstance(spec, dict) else None
        out.nodes.append(
            KgNode(
                id=kg_node_id("service", service_name, rel_path),
                type=KgNodeType.SERVICE,
                name=service_name,
                path=rel_path,
                properties={"class": cls or ""},
                evidence=[evidence_for(rel_path)],
            )
        )


def _extract_config(root: Path, path: Path, out: FrameworkExtraction, *, kind: str) -> None:
    rel_path = rel(root, path)
    data = load_yaml(path)
    for raw_name in data:
        name = str(raw_name)
        out.nodes.append(
            KgNode(
                id=kg_node_id("config", name, rel_path),
                type=KgNodeType.CONFIG,
                name=name,
                path=rel_path,
                properties={"config_kind": kind},
                evidence=[evidence_for(rel_path)],
            )
        )


def _extract_test(root: Path, path: Path, out: FrameworkExtraction) -> None:
    rel_path = rel(root, path)
    if not is_test_path(rel_path) and not path.name.endswith("Test.php"):
        return
    name = path.stem
    out.nodes.append(
        KgNode(
            id=kg_node_id("test", name, rel_path),
            type=KgNodeType.TEST,
            name=name,
            path=rel_path,
            evidence=[evidence_for(rel_path)],
        )
    )
