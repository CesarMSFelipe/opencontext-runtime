"""PR-009 SPEC-MEM-009-13: eight curated project-memory markdown projections."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.project_files import PROJECT_MEMORY_FILES, generate
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef


def _proc_command(store: LocalMemoryStore) -> None:
    now = datetime.now(tz=UTC)
    store.write(
        MemoryRecord(
            id="cmd-1",
            layer=MemoryLayer.PROCEDURAL,
            key="proc:command:tests",
            content="Run the test suite with: python -m pytest tests -q",
            confidence=0.9,
            source_refs=[EvidenceRef(source="run:42", source_type="run", confidence=0.9)],
            decay_policy=DecayPolicy(enabled=False),
            created_at=now,
            updated_at=now,
        )
    )


def test_generate_writes_all_eight_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = LocalMemoryStore(root / ".storage" / "mem.db")
        _proc_command(store)
        written = generate(store, root)
        assert len(written) == 8
        base = root / ".opencontext" / "memory"
        for name in PROJECT_MEMORY_FILES:
            assert (base / name).exists()


def test_commands_md_lists_command_with_evidence_and_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = LocalMemoryStore(root / ".storage" / "mem.db")
        _proc_command(store)
        generate(store, root)
        text = (root / ".opencontext" / "memory" / "commands.md").read_text(encoding="utf-8")
        assert "python -m pytest tests -q" in text
        assert "evidence:" in text
        assert "status:" in text
        assert "run:42" in text
