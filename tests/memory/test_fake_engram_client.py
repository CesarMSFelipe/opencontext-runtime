"""Fake Engram client fixture (PR-AHE-007 task 7.4).

The Engram boundary must NOT require a live Engram server to be exercised. The
recording fake in ``tests/memory/fake_engram_client.py`` replaces the live
transport by implementing the structural ``EngramClient`` Protocol
(memory/engram_mcp_store.py:34) and routing the calls back into an in-process
dict. These tests pin the contract so a future refactor of the wiring cannot
silently require network access again.
"""

from __future__ import annotations

from opencontext_core.memory.engram_mcp_store import EngramClient
from tests.memory.fake_engram_client import FakeEngramClient


def test_fake_satisfies_engram_client_protocol() -> None:
    """The recording fake structurally matches ``EngramClient``.

    ``EngramClient`` is ``@runtime_checkable``; failing this test means the
    fake would never replace a real client (memory/engram_mcp_store.py:34).
    """
    fake = FakeEngramClient()
    assert isinstance(fake, EngramClient)


def test_fake_records_mem_save_calls() -> None:
    """Every mem_save invocation is captured verbatim.

    Routing tests rely on the call log to assert which backend got the record.
    """
    fake = FakeEngramClient()
    fake.mem_save(title="x", content="hello world", type="semantic")
    fake.mem_save(title="y", content="another", type="episodic")
    saves = [call for call in fake.calls if call[0] == "mem_save"]
    assert len(saves) == 2
    titles = [call[1].get("title") for call in saves]
    assert titles == ["x", "y"]


def test_fake_records_mem_search_calls() -> None:
    """mem_search is captured by name + kwargs so routing tests can prove the
    right layer was queried on the right backend."""
    fake = FakeEngramClient()
    fake.mem_search(query="auth", type="semantic")
    assert fake.calls[-1][0] == "mem_search"
    assert fake.calls[-1][1].get("query") == "auth"
    assert fake.calls[-1][1].get("type") == "semantic"


def test_fake_records_mem_update_calls() -> None:
    """mem_update (reinforce / contradict) is captured so curator routing is
    observable in tests, not just writes."""
    fake = FakeEngramClient()
    fake.mem_update(observation_id="rid", action="reinforce")
    fake.mem_update(observation_id="rid", action="contradict", evidence="x")
    updates = [c for c in fake.calls if c[0] == "mem_update"]
    assert len(updates) == 2
    assert updates[0][1]["action"] == "reinforce"
    assert updates[1][1]["action"] == "contradict"


def test_fake_does_not_share_state_across_instances() -> None:
    """Two fakes in the same process never see each other's records.

    Guards against accidental module-level mutable state creeping into the
    EngramClient Protocol surface (every test gets a clean fake).
    """
    a, b = FakeEngramClient(), FakeEngramClient()
    a.mem_save(id="rec-1", title="t", content="c", type="semantic")
    assert b.records == {}
    assert "rec-1" in a.records


def test_fake_replays_saves_in_search_results() -> None:
    """The fake's replay behaviour matches what ``EngramMemoryStore`` consumes:
    a search returns what was saved."""
    fake = FakeEngramClient()
    fake.mem_save(
        id="rid",
        title="auth token",
        content="JWT auth token rotation",
        type="semantic",
    )
    raw = fake.mem_search(query="auth")
    assert "results" in raw
    assert any(r.get("content", "").startswith("JWT") for r in raw["results"])
