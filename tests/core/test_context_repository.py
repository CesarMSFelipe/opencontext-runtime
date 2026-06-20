from __future__ import annotations

from pathlib import Path

from opencontext_core.memory_usability import ContextRepository


def test_context_repository_uses_frontmatter_and_requires_source(tmp_path: Path) -> None:
    repo = ContextRepository(tmp_path)
    item = repo.store("AccessResolver owns access checks.", kind="decision", source="trace:abc")
    path = tmp_path / ".opencontext/context-repository/memory" / f"{item.id}.md"

    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("---\n")
    assert repo.get(item.id).source == "trace:abc"


def test_context_repository_dedups_near_identical_auto_stores(tmp_path: Path) -> None:
    """M5: near-identical harvest summaries must not accrete every run."""
    repo = ContextRepository(tmp_path)
    body = (
        "Goal: add token-based authentication to the login endpoint. "
        "Accomplished: implemented the verify_password helper, wired the session "
        "store, and added regression tests for expiry handling. Discoveries: the "
        "middleware short-circuits on missing headers. Next steps: rate limit the "
        "login route and document the new config keys. Run {rid} completed passed."
    )
    first = repo.store(
        body.format(rid="abc123"),
        kind="summary",
        source="harness:run:abc123",
        collection="summaries",
    )
    # Same summary, only the run id differs — should collapse onto the first.
    second = repo.store(
        body.format(rid="def456"),
        kind="summary",
        source="harness:run:def456",
        collection="summaries",
    )

    assert second.id == first.id
    assert len(list((tmp_path / ".opencontext/context-repository/summaries").glob("*.md"))) == 1


def test_context_repository_promote_and_demote(tmp_path: Path) -> None:
    repo = ContextRepository(tmp_path)
    item = repo.store("Decision content with provenance.", kind="decision", source="trace:abc")

    repo.move(item.id, "system")

    assert (tmp_path / ".opencontext/context-repository/system" / f"{item.id}.md").exists()


def test_context_repository_scores_keyword_entity_and_agent_facts(tmp_path: Path) -> None:
    repo = ContextRepository(tmp_path)
    repo.store(
        "AccessResolver owns access checks.",
        kind="fact",
        source="trace:agent",
        entities={"AccessResolver"},
        agent_generated=True,
    )
    repo.store(
        "Cache warming is handled by PromptCachePlanner.",
        kind="fact",
        source="trace:other",
        entities={"PromptCachePlanner"},
    )

    results = repo.search_results("AccessResolver access policy")

    assert results[0].item.source == "trace:agent"
    assert results[0].matched_entities == ["accessresolver"]
    assert "agent_fact" in results[0].reason


def test_context_repository_search_limit_is_deterministic(tmp_path: Path) -> None:
    repo = ContextRepository(tmp_path)
    repo.store("Pinned team memory.", kind="fact", source="trace:pinned", pin=True)
    repo.store("Unrelated item.", kind="fact", source="trace:other")

    results = repo.search_results("missing", limit=1)

    assert [result.item.source for result in results] == ["trace:pinned"]
