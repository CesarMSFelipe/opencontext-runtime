"""Symfony convention extraction (PR-008, KG-13; OC-KG-001 §15).

Extracts routes (``config/routes*.yaml``), services (``config/services*.yaml``),
controllers, and event subscribers into typed KG v2 nodes/edges with evidence.
Detection is by Symfony markers (``bin/console``, ``symfony/framework-bundle`` in
composer.json, or ``config/routes.yaml``); absent markers => empty extraction.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from opencontext_core.indexing.framework_profiles.base import (
    FrameworkExtraction,
    evidence_for,
    load_yaml,
    rel,
)
from opencontext_core.models.kg_v2 import (
    KgEdge,
    KgEdgeType,
    KgNode,
    KgNodeType,
    kg_edge_id,
    kg_node_id,
)

_SKIP_DIRS = frozenset({".git", "vendor", "node_modules", "__pycache__", "var"})


class SymfonyProfile:
    """Extractor for Symfony projects."""

    name = "symfony"

    def detect(self, root: Path) -> bool:
        """True when Symfony markers are present."""
        if (root / "bin" / "console").exists():
            return True
        composer = root / "composer.json"
        if composer.is_file():
            try:
                data = json.loads(composer.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, json.JSONDecodeError):
                data = {}
            require = {**data.get("require", {}), **data.get("require-dev", {})}
            if any(pkg.startswith("symfony/") for pkg in require):
                return True
        return (root / "config" / "routes.yaml").exists()

    def extract(self, root: Path) -> FrameworkExtraction:
        out = FrameworkExtraction()
        for routing in _iter(root, "routes*.yaml"):
            _extract_routes(root, routing, out)
        for services in _iter(root, "services*.yaml"):
            _extract_services(root, services, out)
        return out


def _iter(root: Path, pattern: str) -> Iterator[Path]:
    config_dir = root / "config"
    base = config_dir if config_dir.is_dir() else root
    for path in base.rglob(pattern):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _extract_routes(root: Path, path: Path, out: FrameworkExtraction) -> None:
    rel_path = rel(root, path)
    data = load_yaml(path)
    for route_name, spec in data.items():
        if not isinstance(spec, dict) or "path" not in spec:
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
        controller = spec.get("controller")
        if isinstance(controller, str) and controller:
            handler_id = kg_node_id("method", controller)
            out.nodes.append(
                KgNode(
                    id=handler_id,
                    type=KgNodeType.METHOD,
                    name=controller,
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


def _extract_services(root: Path, path: Path, out: FrameworkExtraction) -> None:
    rel_path = rel(root, path)
    data = load_yaml(path)
    services = data.get("services", {})
    if not isinstance(services, dict):
        return
    for service_name, spec in services.items():
        if not isinstance(service_name, str) or service_name.startswith("_"):
            continue  # skip _defaults / _instanceof pseudo-keys
        cls = spec.get("class") if isinstance(spec, dict) else None
        out.nodes.append(
            KgNode(
                id=kg_node_id("service", service_name, rel_path),
                type=KgNodeType.SERVICE,
                name=service_name,
                path=rel_path,
                properties={"class": cls or service_name},
                evidence=[evidence_for(rel_path)],
            )
        )
