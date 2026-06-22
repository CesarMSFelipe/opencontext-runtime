"""MemoryHarvester: Observer that extracts learning from harness run results."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from opencontext_core.memory.agent import AgentMemoryStore
from opencontext_core.memory.session_summary import SessionSummary
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord

if TYPE_CHECKING:
    from opencontext_core.memory_usability.context_repository import ContextRepository


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _task_hash(task: str) -> str:
    """Stable sha1 of the task text for memoizing per-task episodic memory records.

    Same task text hashed twice returns the same digest (deterministic), so five
    identical task runs collapse into one ``episodic:task:<sha1>`` upsert key.
    """
    return hashlib.sha1((task or "").encode("utf-8")).hexdigest()[:12]


def _normalize_linked_node(node: str) -> str:
    """Normalize a linked_node string to the ``path[:line]`` shape the boost path uses.

    Accepts:
      - bare symbol name (``validate_token``) — wrapped into ``<name>.py:0``
        so it hashes to a unique missing-context entry per symbol
      - relative source path (``src/auth.py``) — returned as ``<path>:0``
      - already-formatted path[:line] (``src/auth.py:42``) — returned as-is
    Empty / falsy inputs return ``""`` so the caller can filter them out.
    """
    if not node:
        return ""
    text = str(node).strip()
    if not text:
        return ""
    if ":" in text:
        return text
    # Bare symbol names get a synthetic ``<name>.py:0`` so the boost path's
    # basename fuzzy match has a unique file identifier to anchor on.
    if "/" not in text:
        return f"{text}.py:0"
    return f"{text}:0"


def _normalize_linked_nodes(nodes: Any) -> list[str]:
    """Normalize a sequence of linked_nodes to ``path[:line]`` form, deduped + sorted."""
    seen: set[str] = set()
    out: list[str] = []
    for n in nodes or []:
        norm = _normalize_linked_node(str(n))
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _make_record(
    layer: MemoryLayer,
    key: str,
    content: str,
    linked_nodes: list[str] | None = None,
    confidence: float = 0.8,
) -> MemoryRecord:
    now = _now()
    return MemoryRecord(
        id=str(uuid.uuid4()),
        layer=layer,
        key=key,
        content=content,
        confidence=confidence,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=True, half_life_days=90),
        tags=[],
        linked_nodes=linked_nodes or [],
        created_at=now,
        updated_at=now,
    )


class MemoryHarvester:
    """Observer. Called from ArchivePhase after artifact persistence.

    Pattern: Observer — no coupling with HarnessPhase.
    SRP: only harvests, never retrieves.
    """

    def __init__(
        self, store: AgentMemoryStore, context_repo: ContextRepository | None = None
    ) -> None:
        self.store = store
        self._context_repo = context_repo

    def harvest(self, result: Any) -> list[MemoryRecord]:
        """Extract learnings from a HarnessRunResult and write to store.

        Two consistency upgrades relative to the prior implementation:

        * Episodic records are keyed per TASK (sha1 of the task text, not per
          run) so successive identical-task runs UPSERT rather than appending
          five identical \"Task 'X' completed\" breadcrumbs. The MemoryStore.write
          API has no native upsert, so the harvester checks by key first and
          skips the write when a record with that key already exists. This keeps
          recall cheap and avoids burying future procedural / failure signals
          under dozens of identical episodic rows.
        * ``FAILURE:missing_context`` linked_nodes now carry real source paths
          (``path[:line]``) from :attr:`HarnessRunResult.context_omitted_paths`
          when the harness has populated them, not the bare symbol names that
          the previous ``metadata.missing_context`` artifact attribute held. The
          boost path in :class:`RetrievalPlanner._memory_boost_map` matches
          ``item.source`` against these ``path[:line]`` entries — previously it
          matched symbol names against ``fts:`` or ``graph:`` prefixed ids and
          never found anything.
        """
        records: list[MemoryRecord] = []

        task = getattr(result, "task", "unknown")
        run_id = getattr(result, "run_id", "unknown")
        status = getattr(result, "status", "unknown")
        task_hash = _task_hash(task)

        # Episodic keyed per-task (not per-run) so 5 identical runs of the same
        # task collapse into one upsert; recall of "what task ran" stays cheap.
        episodic_key = f"episodic:task:{task_hash}"
        if not self._record_exists(episodic_key):
            episodic = _make_record(
                layer=MemoryLayer.EPISODIC,
                key=episodic_key,
                content=(f"Task '{task}' last completed with status '{status}' (run {run_id})."),
            )
            self.store.write(episodic)
            records.append(episodic)
        # Otherwise: skip — the previous task-version episode remains the canonical one.

        # Procedural: learn from test failures. Keyed per-task (also dedup-guarded).
        if self._has_test_failures(result):
            procedural_key = f"procedural:failure_pattern:{task_hash}"
            if not self._record_exists(procedural_key):
                procedural = _make_record(
                    layer=MemoryLayer.PROCEDURAL,
                    key=procedural_key,
                    content=(
                        f"Task '{task}' had test failures. "
                        "Review test coverage before similar tasks."
                    ),
                    confidence=0.7,
                )
                self.store.write(procedural)
                records.append(procedural)

        # Failure patterns: missing context. Prior to this change linked_nodes
        # only carried bare symbol names (``validate_token``) which the boost
        # path never matched against ``fts:``/``graph:`` ids; ``recent_failure``
        # contributed 0. Two sources for ``missing``:
        #   1. ``state.context_omitted_paths`` (preferred; populated by explore)
        #   2. legacy ``artifact.metadata.missing_context`` (rare)
        missing = self._extract_missing_context(result)
        # Normalize to ``path[:line]`` form (deduped, order-preserving) so the
        # planner's boost path can match against item.source / file / symbol name.
        missing = _normalize_linked_nodes(missing)
        if missing:
            failure_key = f"failure:missing_context:{task_hash}"
            if not self._record_exists(failure_key):
                failure = _make_record(
                    layer=MemoryLayer.FAILURE,
                    key=failure_key,
                    content=(
                        f"Task '{task}' was missing context: "
                        f"{', '.join(missing[:8])}{'...' if len(missing) > 8 else ''}."
                    ),
                    linked_nodes=missing,
                    confidence=0.9,
                )
                self.store.write(failure)
                records.append(failure)

        if self._context_repo is not None:
            self._write_session_summary(result, records)

        return records

    def _write_session_summary(self, result: Any, records: list[MemoryRecord]) -> None:
        """Write human-readable session summary to ContextRepository."""
        try:
            task = getattr(result, "task", "unknown")
            run_id = getattr(result, "run_id", "unknown")
            status = getattr(result, "status", "unknown")
            summary = SessionSummary(
                goal=task,
                accomplished=[f"Run {run_id} completed with status '{status}'."],
                discoveries=[r.content for r in records if r.layer == MemoryLayer.PROCEDURAL],
                next_steps=[r.content for r in records if r.layer == MemoryLayer.FAILURE],
            )
            assert self._context_repo is not None
            self._context_repo.store(
                summary.to_markdown(),
                kind="summary",
                source=f"harness:run:{run_id}",
                collection="summaries",
            )
        except Exception:
            pass  # summary write is best-effort

    def _has_test_failures(self, result: Any) -> bool:
        """Check if any gate with 'test' in the id has failed."""
        gates = getattr(result, "gates", [])
        for gate in gates:
            gate_id = getattr(gate, "id", "") or ""
            status = getattr(gate, "status", None)
            if "test" in gate_id.lower() and str(status).lower() in ("failed", "failure"):
                return True
        # Also check ledgers for error statuses
        ledgers = getattr(result, "ledgers", [])
        for ledger in ledgers:
            ledger_status = getattr(ledger, "status", "") or ""
            if "fail" in str(ledger_status).lower():
                return True
        return False

    def _extract_missing_context(self, result: Any) -> list[str]:
        """Extract symbols/files that were identified as missing from the run.

        Two sources, in priority order:

        1. ``HarnessRunResult.context_omitted_paths`` — the explore phase's
           source-path list of items the pack dropped. Populated by
           :class:`ExplorePhase.run` from ``pack.omitted`` and passed via
           ``HarnessState``. This is the canonical signal post-fix; the boost
           path matches against ``path[:line]`` exactly.
        2. Legacy ``artifact.metadata.missing_context`` list. Empty on the
           current harness path (the explore metadata block does not set it on
           artifacts anymore), but kept for any wired-in caller that still
           populates it.
        """
        missing: list[str] = []
        # Source 1: state.context_omitted_paths (preferred).
        state_like = getattr(result, "state", None)
        if state_like is None:
            # HarnessRunResult doesn't carry ``state`` directly; the harvester
            # is invoked from ArchivePhase where ``state`` is a method-local.
            # Caller can also pass ``HarnessState`` as ``state``; both paths
            # are tolerated.
            state_like = result
        omitted_paths = getattr(state_like, "context_omitted_paths", None) or []
        if isinstance(omitted_paths, list):
            missing.extend(str(p) for p in omitted_paths if p)
        # Source 2: legacy artifact metadata (best-effort).
        artifacts = getattr(result, "artifacts", [])
        for artifact in artifacts:
            meta = getattr(artifact, "metadata", {}) or {}
            missing_ctx = meta.get("missing_context", [])
            if isinstance(missing_ctx, list):
                missing.extend(str(p) for p in missing_ctx if p)
        return missing

    def _record_exists(self, key: str) -> bool:
        """True when a memory record with ``key`` is already in the store.

        ``AgentMemoryStore.write`` has no native upsert, so the harvester pre-
        checks by key (across all layers) before writing so identical-task
        runs collapse rather than accumulate duplicates. Best-effort: any
        failure to search returns ``False`` so the write proceeds (correctness
        precedes perfect dedup on broken stores).
        """
        try:
            for rec in self.store.search(key, scope=None, limit=64):
                if getattr(rec, "key", None) == key:
                    return True
        except Exception:
            return False
        return False
