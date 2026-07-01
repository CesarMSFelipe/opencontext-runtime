"""PR-008 KG v2 schema tests — T008a.3.

REQ_kg_v2_001: schema round-trip + temporal metadata.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from opencontext_core.graph.v2.schema import (
    KgEdge,
    KgEdgeType,
    KgNode,
    KgNodeType,
    TemporalMetadata,
)


class TestSchemaRoundTrip:
    def test_node_round_trip(self) -> None:
        node = KgNode(
            id="n:file:src/main.py",
            type=KgNodeType.FILE,
            name="main.py",
            properties={"path": "src/main.py", "language": "python"},
        )
        data = node.model_dump(mode="json")
        assert data["id"] == "n:file:src/main.py"
        assert data["type"] == "file"
        restored = KgNode(**data)
        assert restored == node

    def test_edge_round_trip(self) -> None:
        edge = KgEdge(
            id="e:calls:n1:n2",
            type=KgEdgeType.CALLS,
            source="n:func:foo",
            target="n:func:bar",
        )
        data = edge.model_dump(mode="json")
        assert data["type"] == "calls"
        restored = KgEdge(**data)
        assert restored == edge


class TestTemporalMetadata:
    def test_temporal_superseded(self) -> None:
        """REQ_kg_v2_001: temporal metadata tracks superseded_at."""
        ts1 = TemporalMetadata(created_at=datetime(2026, 1, 1, tzinfo=UTC))
        ts2 = TemporalMetadata(
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            superseded_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        assert ts1.superseded_at is None
        assert ts1.is_active is True
        assert ts2.superseded_at is not None
        assert ts2.is_active is False

    def test_temporal_json_serializable(self) -> None:
        ts = TemporalMetadata(created_at=datetime.now(tz=UTC))
        data = json.loads(ts.model_dump_json())
        assert "created_at" in data


class TestNodeTypes:
    def test_23_node_types_defined(self) -> None:
        values = {e.value for e in KgNodeType}
        assert len(values) == 23

    def test_file_type_present(self) -> None:
        assert KgNodeType.FILE.value == "file"


class TestEdgeTypes:
    def test_21_edge_types_defined(self) -> None:
        values = {e.value for e in KgEdgeType}
        assert len(values) == 21

    def test_calls_type_present(self) -> None:
        assert KgEdgeType.CALLS.value == "calls"
