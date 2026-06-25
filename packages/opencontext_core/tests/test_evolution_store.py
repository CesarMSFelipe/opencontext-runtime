from __future__ import annotations

import pytest

from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.learning.evolution_store import EvolutionStore


def _proposal(
    proposal_id: str, kind: str = "context_weight", status: str = "proposed"
) -> EvolutionProposal:
    return EvolutionProposal(
        proposal_id=proposal_id,
        kind=kind,
        title=f"Proposal {proposal_id}",
        rationale="test rationale",
        status=status,
    )


@pytest.fixture()
def store(tmp_path) -> EvolutionStore:
    # Pass the store dir directly (not project root) to keep tests isolated
    store_dir = tmp_path / "learning" / "evolution"
    return EvolutionStore(store_dir)


class TestEvolutionStoreSave:
    def test_save_creates_json_file(self, store, tmp_path):
        store.save(_proposal("abc-001"))
        files = list((tmp_path / "learning" / "evolution").glob("*.json"))
        assert len(files) == 1

    def test_saved_file_is_named_by_proposal_id(self, store, tmp_path):
        store.save(_proposal("my-proposal-id"))
        assert (tmp_path / "learning" / "evolution" / "my-proposal-id.json").exists()

    def test_save_is_idempotent(self, store):
        p = _proposal("dup-id")
        store.save(p)
        store.save(p)
        assert len(store.list()) == 1


class TestEvolutionStoreGet:
    def test_get_retrieves_saved_proposal(self, store):
        store.save(_proposal("fetch-me", kind="budget_profile"))
        retrieved = store.get("fetch-me")
        assert retrieved is not None
        assert retrieved.proposal_id == "fetch-me"
        assert retrieved.kind == "budget_profile"

    def test_get_returns_none_for_unknown_id(self, store):
        assert store.get("does-not-exist") is None

    def test_load_alias_works(self, store):
        store.save(_proposal("alias-test"))
        assert store.load("alias-test") is not None


class TestEvolutionStoreList:
    def test_list_returns_all_proposals(self, store):
        for i in range(3):
            store.save(_proposal(f"p-{i}"))
        results = store.list()
        assert len(results) == 3
        assert {r.proposal_id for r in results} == {"p-0", "p-1", "p-2"}

    def test_list_returns_empty_when_dir_does_not_exist(self, tmp_path):
        empty_store = EvolutionStore(tmp_path / "nonexistent" / "evolution")
        assert empty_store.list() == []

    def test_list_by_status_filters_correctly(self, store):
        store.save(_proposal("prop-a", status="proposed"))
        store.save(_proposal("prop-b", status="approved"))
        store.save(_proposal("prop-c", status="proposed"))
        proposed = store.list_by_status("proposed")
        assert len(proposed) == 2
        assert all(p.status == "proposed" for p in proposed)


class TestEvolutionStoreUpdate:
    def test_update_status_overwrites_status(self, store):
        store.save(_proposal("upd-001", status="proposed"))
        store.update_status("upd-001", "approved")
        retrieved = store.get("upd-001")
        assert retrieved is not None
        assert retrieved.status == "approved"

    def test_update_with_kwargs_changes_field(self, store):
        store.save(_proposal("upd-002"))
        store.update("upd-002", confidence=0.95)
        retrieved = store.get("upd-002")
        assert retrieved is not None
        assert retrieved.confidence == pytest.approx(0.95)

    def test_update_returns_none_for_nonexistent_proposal(self, store):
        assert store.update("ghost-id", status="approved") is None

    def test_update_status_returns_none_for_nonexistent_proposal(self, store):
        assert store.update_status("ghost-id", "approved") is None
