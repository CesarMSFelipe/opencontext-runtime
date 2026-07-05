"""Tests for organization-graph-ownership (PR-R2-H).

REQ-org-graph-001..004 — OwnerRef + CODEOWNERS + Resolver.
"""

from __future__ import annotations

from datetime import UTC, datetime


class TestOwnerRef:
    def test_owner_ref_round_trip(self) -> None:
        from opencontext_core.organization.graph import OwnerRef

        ts = datetime(2026, 7, 1, tzinfo=UTC)
        ref = OwnerRef(
            source="codeowners",
            username="alice",
            email="alice@example.com",
            last_verified=ts,
        )
        data = ref.model_dump()
        # Pydantic round-trip
        restored = OwnerRef.model_validate(data)
        assert restored.source == "codeowners"
        assert restored.username == "alice"
        assert restored.email == "alice@example.com"
        assert restored.last_verified == ts

    def test_owner_ref_source_enum(self) -> None:
        from opencontext_core.organization.graph import OwnerRef

        ref = OwnerRef(
            source="git",
            username="bob",
            last_verified=datetime.now(UTC),
        )
        assert ref.source == "git"


class TestOrgGraph:
    def test_org_node_fields(self) -> None:
        from opencontext_core.organization.graph import OrgNode

        node = OrgNode(
            id="team-platform",
            kind="team",
            name="Platform Team",
        )
        assert node.id == "team-platform"
        assert node.kind == "team"

    def test_org_edge_fields(self) -> None:
        from opencontext_core.organization.graph import OrgEdge

        edge = OrgEdge(src="team-platform", dst="repo-core", relation="owns")
        assert edge.src == "team-platform"
        assert edge.dst == "repo-core"
        assert edge.relation == "owns"


class TestBuildOrgGraph:
    def test_build_minimal_graph(self) -> None:
        from opencontext_core.organization.graph import OrgNode, build_org_graph

        nodes = [OrgNode(id="a", kind="team", name="A")]
        graph = build_org_graph(nodes=nodes, edges=[])
        assert graph.find_owner("a") is not None

    def test_find_owner_returns_team(self) -> None:
        from opencontext_core.organization.graph import (
            OrgEdge,
            OrgNode,
            TeamOwnership,
            build_org_graph,
        )

        nodes = [
            OrgNode(id="team-platform", kind="team", name="Platform"),
            OrgNode(id="repo-core", kind="repo", name="Core"),
        ]
        edges = [OrgEdge(src="team-platform", dst="repo-core", relation="owns")]
        ownership = [
            TeamOwnership(team_id="team-platform", scope="repo:repo-core"),
        ]
        graph = build_org_graph(nodes=nodes, edges=edges, ownership=ownership)
        owner = graph.find_owner("repo:repo-core")
        assert owner is not None
        assert owner.id == "team-platform"


class TestTeamOwnershipDataclass:
    def test_fields(self) -> None:
        from opencontext_core.organization.graph import TeamOwnership

        t = TeamOwnership(team_id="team-platform", scope="repo:core")
        assert t.team_id == "team-platform"
        assert t.scope == "repo:core"


class TestCodeownersParser:
    def test_nested_pattern_matches(self) -> None:
        from opencontext_core.organization.graph import (
            CODEOWNERSFile,
            OwnerResolver,
        )

        text = "/packages/*/src/** OWNERS @team-platform\n"
        co = CODEOWNERSFile.parse(text)
        resolver = OwnerResolver(codeowners=co)
        ref = resolver.resolve("/packages/opencontext_core/src/foo.py")
        assert ref.source == "codeowners"
        assert ref.username == "@team-platform"

    def test_non_matching_path_returns_unknown(self) -> None:
        from opencontext_core.organization.graph import (
            CODEOWNERSFile,
            OwnerResolver,
        )

        text = "/packages/*/src/** OWNERS @team-platform\n"
        co = CODEOWNERSFile.parse(text)
        resolver = OwnerResolver(codeowners=co)
        ref = resolver.resolve("/docs/random.md")
        assert ref.source == "unknown"
