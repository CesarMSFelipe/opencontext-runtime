"""PR-008 KG v2 framework extraction: Drupal routing.yml -> route nodes (KG-13)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.framework_profiles import (
    DrupalProfile,
    SymfonyProfile,
    extract_framework_facts,
)
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.models.kg_v2 import KgEdgeType, KgNodeType

_DRUPAL_ROUTING = """\
my_module.content:
  path: '/my/path'
  defaults:
    _controller: '\\\\Drupal\\\\my_module\\\\Controller\\\\MyController::content'
  requirements:
    _permission: 'access content'
"""

_SYMFONY_ROUTES = """\
app_home:
  path: /
  controller: App\\Controller\\HomeController::index
"""


def test_drupal_routing_extracted_as_facts(tmp_path: Path) -> None:
    (tmp_path / "my_module.routing.yml").write_text(_DRUPAL_ROUTING, encoding="utf-8")

    assert DrupalProfile().detect(tmp_path) is True
    extraction = extract_framework_facts(tmp_path)
    route_nodes = [n for n in extraction.nodes if n.type == KgNodeType.ROUTE]
    assert any(n.name == "my_module.content" for n in route_nodes)
    # Route is linked to its controller handler via a ROUTES_TO edge.
    assert any(e.type == KgEdgeType.ROUTES_TO for e in extraction.edges)
    # Every extracted fact carries evidence (OC-KG-001 §11).
    assert all(n.evidence for n in route_nodes)


def test_index_framework_facts_persists_route_nodes(tmp_path: Path) -> None:
    (tmp_path / "my_module.routing.yml").write_text(_DRUPAL_ROUTING, encoding="utf-8")
    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"), project_id="proj")
    try:
        count = kg.index_framework_facts(tmp_path)
        assert count >= 1
        conn = kg.db._connect()
        routes = conn.execute("SELECT name FROM nodes WHERE kind = 'route'").fetchall()
        assert any(r["name"] == "my_module.content" for r in routes)
        edges = conn.execute("SELECT 1 FROM edges WHERE kind = 'routes_to'").fetchall()
        assert edges
    finally:
        kg.close()


def test_symfony_detected_and_routes_extracted(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "routes.yaml").write_text(_SYMFONY_ROUTES, encoding="utf-8")

    assert SymfonyProfile().detect(tmp_path) is True
    extraction = extract_framework_facts(tmp_path)
    assert any(n.type == KgNodeType.ROUTE and n.name == "app_home" for n in extraction.nodes)


def test_no_framework_yields_empty(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    extraction = extract_framework_facts(tmp_path)
    assert extraction.nodes == []
    assert extraction.edges == []
