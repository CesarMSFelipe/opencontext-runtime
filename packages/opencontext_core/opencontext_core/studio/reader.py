"""StudioReader — read-only projection of ``.opencontext/`` into Studio views.

OBSERVE ONLY (SPEC-STU-014-11): no method here writes to disk or mutates
runtime state. Every reader opens artifacts read-only and projects them into the
framework-free view models in :mod:`opencontext_core.studio.views`. A broken or
missing artifact degrades to an empty/``available=False`` view rather than
raising, so Studio stays robust over partial evidence.

Sources (today's public-contract analogues):
  * sessions  → ``runtime.session_store.SessionStore`` (``.opencontext/sessions``)
                and the legacy ``oc_new.store.OcNewStore`` (``.opencontext/runs``)
  * live      → ``runtime.session.LiveState`` (``live-state.json``)
  * events    → ``events.jsonl`` (16 categories, doc 59) → timeline lanes (doc 60)
  * timeline  → ``oc_new.models.OcNewRunState.phases`` (persona/skill, gate)
  * receipts  → ``operating_model.receipts.RunReceipt`` (+ ``receipt.json``)
  * harness   → ``harness-report.json`` (``harness.models.HarnessReport``)
  * cost      → ``operating_model.receipts.ProviderReceipt``
  * kg        → ``indexing.knowledge_graph.KnowledgeGraph`` (search by task)
  * capability→ ``capabilities.detector.build_capability_graph``
  * decisions → ``runtime.run.RuntimeRun.decision_log``
  * learning  → ``learning.candidate_extractor.LearningCandidate``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_core.paths import StorageMode, resolve_workspace_path
from opencontext_core.studio.views import (
    StudioBenchmarkCoverageView,
    StudioBenchmarkSuiteCoverage,
    StudioBrainView,
    StudioCacheView,
    StudioCapabilityNode,
    StudioCapabilityView,
    StudioConfigView,
    StudioContextLayer,
    StudioContextView,
    StudioCostView,
    StudioDecision,
    StudioDecisionLogView,
    StudioEvent,
    StudioEventLane,
    StudioGateResult,
    StudioHarnessView,
    StudioKgNode,
    StudioKgView,
    StudioLearningCandidate,
    StudioLearningView,
    StudioMemoryRecord,
    StudioMemoryView,
    StudioReceipt,
    StudioReceiptView,
    StudioReleaseGateView,
    StudioSession,
    StudioTaskHistoryView,
    StudioTaskStatus,
    StudioTimeline,
    StudioTimelineNode,
    StudioTimelines,
)

# OC Flow honesty statuses (B1/AVH-011) surfaced by the N2 task-history view.
_BLOCKED_STATUSES: tuple[str, ...] = (
    "blocked",
    "escalated",
    "needs_executor",
    "needs_provider",
    "needs_user_edit",
)

# Event-family lanes (doc 60 item 12) → required event categories (doc 59).
_LANES: dict[str, list[str]] = {
    "execution": ["session", "workflow", "node", "persona", "skill", "provider"],
    "decision": ["policy", "escalation", "diagnosis", "inspection"],
    "context": ["context"],
    "memory": ["memory", "consolidation"],
    "kg": ["kg"],
}


class StudioReader:
    """Read-only projection of ``.opencontext/`` into Studio view models."""

    def __init__(self, root: Path | str = ".") -> None:
        self._root = Path(root)

    # ------------------------------------------------------------- internals
    def _load_json(self, path: Path) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _session_store(self) -> Any:
        from opencontext_core.runtime.session_store import SessionStore

        return SessionStore(self._root)

    def _oc_store(self) -> Any:
        from opencontext_core.oc_new.store import OcNewStore

        return OcNewStore(self._root)

    def _session_ids(self) -> list[str]:
        path = resolve_workspace_path(self._root, StorageMode.local) / "sessions"
        if not path.exists():
            return []
        return [p.name for p in path.iterdir() if (p / "session.json").exists()]

    def _resolve(self, sid: str) -> tuple[str | None, Any]:
        """Return ``("session", session)``, ``("run", state)``, or ``(None, None)``."""
        store = self._session_store()
        if store.session_exists(sid):
            try:
                return "session", store.load_session(sid)
            except Exception:
                return None, None
        try:
            return "run", self._oc_store().load(sid)
        except Exception:
            return None, None

    def _run_artifact_dirs(self, sid: str, kind: str) -> list[Path]:
        """Directories that may hold ``receipt.json`` / ``harness-report.json``."""
        if kind == "run":
            return [self._oc_store().run_dir(sid)]
        base = resolve_workspace_path(self._root, StorageMode.local) / "sessions" / sid
        dirs = [base]
        runs = base / "runs"
        if runs.exists():
            dirs.extend(p for p in runs.iterdir() if p.is_dir())
        return dirs

    def _find_artifact(self, sid: str, kind: str, filename: str) -> Path | None:
        for directory in self._run_artifact_dirs(sid, kind):
            candidate = directory / filename
            if candidate.exists():
                return candidate
        return None

    # ------------------------------------------------------------- sessions
    def list_sessions(self) -> list[StudioSession]:
        """All sessions/runs, newest-first (SPEC-STU-014-02/03)."""
        sessions: list[StudioSession] = []
        for sid in self._session_ids():
            kind, obj = self._resolve(sid)
            if kind == "session":
                sessions.append(self._session_from_runtime(obj))
        for state in self._oc_store().list_runs():
            sessions.append(self._session_from_run(state))
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def session(self, sid: str) -> StudioSession | None:
        """One session/run by id, or ``None`` when absent."""
        kind, obj = self._resolve(sid)
        if kind == "session":
            return self._session_from_runtime(obj)
        if kind == "run":
            return self._session_from_run(obj)
        return None

    def _session_from_runtime(self, session: Any) -> StudioSession:
        live = None
        try:
            live = self._session_store().load_live_state(session.session_id)
        except Exception:
            live = None
        return StudioSession(
            id=session.session_id,
            kind="session",
            task=session.task,
            workflow=getattr(live, "workflow", None),
            profile=session.profile,
            status=str(session.status),
            current_node=getattr(live, "node", None),
            next_action=getattr(live, "message", None),
            updated_at=session.updated_at,
        )

    def _session_from_run(self, state: Any) -> StudioSession:
        next_action = getattr(state, "next_action", None)
        profile = None
        config = getattr(state, "config", None)
        if config is not None:
            profile = str(getattr(getattr(config, "preset", ""), "value", "") or "") or None
        return StudioSession(
            id=state.identity.run_id,
            kind="run",
            task=state.task,
            workflow=profile,
            profile=profile,
            status=self._run_status(state),
            current_node=state.current_phase,
            elapsed_s=self._run_elapsed(state),
            next_action=getattr(next_action, "instruction", None),
            updated_at=str(state.updated_at),
        )

    @staticmethod
    def _run_status(state: Any) -> str:
        statuses = {p.status for p in state.phases}
        if "failed" in statuses:
            return "failed"
        if getattr(state, "blocked_reason", None):
            return "blocked"
        if "running" in statuses:
            return "running"
        if state.phases and all(p.status in {"passed", "warning", "skipped"} for p in state.phases):
            return "completed"
        return "pending"

    @staticmethod
    def _run_elapsed(state: Any) -> float | None:
        starts = [p.started_at for p in state.phases if p.started_at]
        ends = [p.completed_at for p in state.phases if p.completed_at]
        if not starts or not ends:
            return None
        try:
            return float(max((max(ends) - min(starts)).total_seconds(), 0.0))
        except Exception:
            return None

    # ------------------------------------------------------------- timeline
    def timeline(self, sid: str) -> StudioTimeline:
        """Workflow timeline with persona/skill and gate state (SPEC-STU-014-04)."""
        kind, obj = self._resolve(sid)
        if kind == "run":
            return self._timeline_from_run(obj)
        if kind == "session":
            return self._timeline_from_events(obj)
        return StudioTimeline(session_id=sid)

    def _timeline_from_run(self, state: Any) -> StudioTimeline:
        # Canonical phase->persona/skill plan (oc_new/flow.py). AgenticFlowConfig
        # carries no per-phase persona/skill, so the flow plan is the real source.
        from opencontext_core.oc_new.flow import OC_NEW_FLOW

        defs = {d.name: d for d in OC_NEW_FLOW}
        nodes = [
            StudioTimelineNode(
                name=str(p.name),
                status=str(p.status),
                persona=getattr(defs.get(p.name), "persona", None),
                skill=getattr(defs.get(p.name), "skill", None),
                gate_blocked=(
                    getattr(state, "blocked_reason", None) is not None
                    and state.current_phase == p.name
                ),
                gate_reason=(state.blocked_reason if state.current_phase == p.name else None),
                warnings=list(p.warnings),
                started_at=str(p.started_at) if p.started_at else None,
                completed_at=str(p.completed_at) if p.completed_at else None,
            )
            for p in state.phases
        ]
        return StudioTimeline(
            session_id=state.identity.run_id, current_node=state.current_phase, nodes=nodes
        )

    def _timeline_from_events(self, session: Any) -> StudioTimeline:
        events = self._read_events(session.session_id)
        order: list[str] = []
        by_node: dict[str, StudioTimelineNode] = {}
        for ev in events:
            node = ev.get("node_id") or ev.get("workflow_id")
            if not node or ev.get("type", "").split(".", 1)[0] != "node":
                continue
            if node not in by_node:
                by_node[node] = StudioTimelineNode(name=str(node))
                order.append(node)
            by_node[node].status = str(ev.get("status", by_node[node].status))
        current = None
        try:
            current = self._session_store().load_live_state(session.session_id).node
        except Exception:
            current = None
        return StudioTimeline(
            session_id=session.session_id,
            current_node=current,
            nodes=[by_node[n] for n in order],
        )

    def _read_events(self, sid: str) -> list[dict[str, Any]]:
        path = (
            resolve_workspace_path(self._root, StorageMode.local)
            / "sessions"
            / sid
            / "events.jsonl"
        )
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        return events

    def timelines(self, sid: str) -> StudioTimelines:
        """Event-family timelines: execution/decision/context/memory/kg (doc 60 item 12)."""
        events = self._read_events(sid)
        if not events:
            return StudioTimelines(session_id=sid, available=False)
        lanes: list[StudioEventLane] = []
        for lane, cats in _LANES.items():
            lane_events = [
                StudioEvent(
                    event_id=str(ev.get("event_id", "")),
                    ts=str(ev.get("created_at", "")),
                    category=str(ev.get("type", "")).split(".", 1)[0],
                    type=str(ev.get("type", "")),
                    status=str(ev.get("status", "")),
                    message=str(ev.get("message", "")),
                    node=ev.get("node_id"),
                )
                for ev in events
                if str(ev.get("type", "")).split(".", 1)[0] in cats
            ]
            lanes.append(StudioEventLane(lane=lane, categories=cats, events=lane_events))
        return StudioTimelines(session_id=sid, available=True, lanes=lanes)

    # -------------------------------------------------------------- context
    def context(self, sid: str) -> StudioContextView:
        """Context-envelope viewer + budget breakdown (SPEC-STU-014-05, STU-CONV)."""
        kind, _ = self._resolve(sid)
        if kind is None:
            return StudioContextView(session_id=sid)
        path = self._find_artifact(sid, kind, "context-report.json")
        data = self._load_json(path) if path else None
        if not isinstance(data, dict):
            return StudioContextView(session_id=sid, available=False)
        layers = [
            StudioContextLayer(
                name=str(layer.get("name", "")),
                token_budget=int(layer.get("token_budget", layer.get("budget", 0)) or 0),
                tokens_used=int(layer.get("tokens_used", layer.get("tokens", 0)) or 0),
                sources=[str(s) for s in layer.get("sources", [])],
            )
            for layer in data.get("layers", [])
            if isinstance(layer, dict)
        ]
        return StudioContextView(
            session_id=sid,
            available=True,
            layers=layers,
            evidence_refs=self._str_list(data.get("evidence_refs") or data.get("evidence")),
            omissions=self._str_list(data.get("omissions")),
            token_budget=int(data.get("token_budget", 0) or 0),
            compression_receipts=self._str_list(data.get("compression_receipts")),
        )

    # ------------------------------------------------------------------- kg
    def kg(self, sid: str, limit: int = 25) -> StudioKgView:
        """Relevant KG subgraph for the session task (SPEC-STU-014-06)."""
        session = self.session(sid)
        if session is None:
            return StudioKgView(session_id=sid)
        try:
            from opencontext_core.config_resolver import resolve_active_storage_file
            from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

            db = resolve_active_storage_file(self._root, "context_graph.db")
            kg = KnowledgeGraph(db_path=str(db))
            if kg.get_stats().get("nodes", 0) == 0:
                return StudioKgView(session_id=sid, available=False, query=session.task)
            results = kg.search(session.task or "", limit=limit)
        except Exception:
            return StudioKgView(session_id=sid, available=False, query=session.task)
        nodes = [
            StudioKgNode(
                id=str(r.get("id", r.get("name", ""))),
                kind=str(r.get("kind", "")),
                name=str(r.get("name", "")),
                path=str(r.get("file_path", r.get("path", ""))),
            )
            for r in results
        ]
        return StudioKgView(
            session_id=sid, available=bool(nodes), query=session.task or "", nodes=nodes
        )

    # -------------------------------------------------------------- memory
    def memory(self, sid: str) -> StudioMemoryView:
        """Memory viewer with lifecycle markers (SPEC-STU-014-07)."""
        kind, _ = self._resolve(sid)
        if kind is None:
            return StudioMemoryView(session_id=sid)
        path = self._find_artifact(sid, kind, "memory-report.json")
        data = self._load_json(path) if path else None
        if not isinstance(data, dict):
            return StudioMemoryView(session_id=sid, available=False)
        records = [
            StudioMemoryRecord(
                id=str(rec.get("id", "")),
                content=str(rec.get("content", "")),
                status=str(rec.get("status", "")),
                superseded=bool(rec.get("superseded", rec.get("superseded_by"))),
                superseded_by=rec.get("superseded_by"),
                conflict=rec.get("conflict"),
            )
            for rec in data.get("records", [])
            if isinstance(rec, dict)
        ]
        return StudioMemoryView(
            session_id=sid,
            available=True,
            records=records,
            conflicts=[str(c) for c in data.get("conflicts", [])],
        )

    # ------------------------------------------------------------- receipts
    def receipts(self, sid: str) -> StudioReceiptView:
        """Patch / receipts viewer with checksums (SPEC-STU-014-08)."""
        kind, _ = self._resolve(sid)
        if kind is None:
            return StudioReceiptView(session_id=sid)
        receipts: list[StudioReceipt] = []
        changed_files: list[str] = []

        # Phase-level receipt (PhaseResultEnvelope) — changed files, risks, status.
        rpath = self._find_artifact(sid, kind, "receipt.json")
        rdata = self._load_json(rpath) if rpath else None
        if isinstance(rdata, dict):
            artifacts = [str(a) for a in rdata.get("artifacts", [])]
            changed_files.extend(artifacts)
            receipts.append(
                StudioReceipt(
                    run_id=str(rdata.get("run_id", "")),
                    change_id=str(rdata.get("change_id", "")),
                    phase=str(rdata.get("phase", "")),
                    status=str(rdata.get("status", "")),
                    duration_s=float(rdata.get("duration_s", 0.0) or 0.0),
                    summary=str(rdata.get("executive_summary", "")),
                    risks=[str(r) for r in rdata.get("risks", [])],
                    missing_artifacts=[str(m) for m in rdata.get("missing_artifacts", [])],
                )
            )

        # Run-level receipt (RunReceipt) — checksums (policy/context/prompt/envelope/artifacts).
        try:
            from opencontext_core.operating_model.receipts import RunReceiptStore

            for rr in RunReceiptStore(self._root).list():
                if kind == "run" and rr.run_id != sid:
                    continue
                receipts.append(
                    StudioReceipt(
                        run_id=rr.run_id,
                        status=str(rr.quality_status or ""),
                        summary=f"{rr.provider}/{rr.model}",
                        checksums={
                            "policy_hash": rr.policy_hash,
                            "context_pack_hash": rr.context_pack_hash,
                            "prompt_hash": rr.prompt_hash,
                            "envelope_hash": rr.envelope_hash or "",
                            "artifacts_hash": rr.artifacts_hash or "",
                        },
                    )
                )
        except Exception:
            pass

        return StudioReceiptView(
            session_id=sid,
            available=bool(receipts),
            changed_files=changed_files,
            receipts=receipts,
        )

    # -------------------------------------------------------------- harness
    def harness(self, sid: str) -> StudioHarnessView:
        """Harness / gates view (SPEC-STU-014-08)."""
        kind, _ = self._resolve(sid)
        if kind is None:
            return StudioHarnessView(session_id=sid)
        path = self._find_artifact(sid, kind, "harness-report.json")
        data = self._load_json(path) if path else None
        if not isinstance(data, dict):
            return StudioHarnessView(session_id=sid, available=False)
        return StudioHarnessView(
            session_id=sid,
            available=True,
            passed=bool(data.get("passed", False)),
            failures=[str(f) for f in data.get("failures", [])],
            duration_s=float(data.get("duration_s", 0.0) or 0.0),
            run_id=str(data.get("run_id", "")),
            change_id=str(data.get("change_id", "")),
        )

    # ----------------------------------------------------------------- cost
    def cost(self, sid: str) -> StudioCostView:
        """Cost dashboard: estimate vs actual + token savings (SPEC-STU-014-09)."""
        try:
            from opencontext_core.operating_model.receipts import RunReceiptStore

            provider_receipts = RunReceiptStore(self._root).list_provider_receipts()
        except Exception:
            provider_receipts = []
        if not provider_receipts:
            return StudioCostView(session_id=sid, available=False)
        estimated = sum(r.estimated_cost for r in provider_receipts)
        input_tokens = sum(r.input_tokens for r in provider_receipts)
        output_tokens = sum(r.output_tokens for r in provider_receipts)
        cached = sum(r.input_tokens for r in provider_receipts if r.cache_hit)
        return StudioCostView(
            session_id=sid,
            available=True,
            estimated_cost=round(estimated, 6),
            actual_cost=round(estimated, 6),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
            token_savings=cached,
            calls=len(provider_receipts),
        )

    # --------------------------------------------------------- capabilities
    def capabilities(self) -> StudioCapabilityView:
        """Capability Graph view with remediation (STU-CONV)."""
        try:
            from opencontext_core.capabilities.detector import build_capability_graph

            graph = build_capability_graph(self._root)
        except Exception:
            return StudioCapabilityView(available=False)
        nodes = []
        for node in graph.nodes:
            unmet = graph.unmet_dependencies(node.id)
            remediation = ""
            if not node.available:
                remediation = f"Install or enable '{node.id}' to use dependent workflows."
            elif unmet:
                remediation = f"Resolve dependencies: {', '.join(unmet)}."
            nodes.append(
                StudioCapabilityNode(
                    id=node.id,
                    available=node.available,
                    evidence=node.evidence,
                    version=node.version,
                    unmet_dependencies=unmet,
                    remediation=remediation,
                )
            )
        return StudioCapabilityView(available=bool(nodes), nodes=nodes)

    # ------------------------------------------------------------ decisions
    def decision_log(self, sid: str) -> StudioDecisionLogView:
        """Decision Log view (rationale only, no chain-of-thought) (STU-CONV)."""
        entries = self._collect_decisions(sid)
        if entries is None:
            return StudioDecisionLogView(session_id=sid, available=False)
        return StudioDecisionLogView(session_id=sid, available=bool(entries), decisions=entries)

    def _collect_decisions(self, sid: str) -> list[StudioDecision] | None:
        kind, _ = self._resolve(sid)
        if kind != "session":
            return None
        base = resolve_workspace_path(self._root, StorageMode.local) / "sessions" / sid / "runs"
        if not base.exists():
            return None
        out: list[StudioDecision] = []
        found = False
        for run_json in base.glob("*/run.json"):
            data = self._load_json(run_json)
            if not isinstance(data, dict):
                continue
            found = True
            log = data.get("decision_log") or {}
            for entry in log.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                out.append(
                    StudioDecision(
                        id=str(entry.get("id", entry.get("entry_id", ""))),
                        kind=str(entry.get("kind", entry.get("selection_kind", ""))),
                        chosen=str(entry.get("chosen", entry.get("decision", ""))),
                        rationale=str(entry.get("rationale", "")),
                        confidence=entry.get("confidence"),
                        created_at=str(entry.get("created_at", "")),
                    )
                )
        return out if found else None

    # ---------------------------------------------------------------- brain
    def brain(self, sid: str) -> StudioBrainView:
        """Runtime Brain / Scheduler view: recommended next node (STU-CONV)."""
        kind, obj = self._resolve(sid)
        if kind == "run":
            next_action = getattr(obj, "next_action", None)
            if next_action is None:
                return StudioBrainView(session_id=sid, available=False)
            return StudioBrainView(
                session_id=sid,
                available=True,
                recommended_next_node=getattr(next_action, "phase", None),
                persona=getattr(next_action, "persona", None),
                rationale=getattr(next_action, "instruction", ""),
                governed_by="oc_new state machine",
            )
        if kind == "session":
            try:
                live = self._session_store().load_live_state(sid)
            except Exception:
                return StudioBrainView(session_id=sid, available=False)
            return StudioBrainView(
                session_id=sid,
                available=live.node is not None,
                recommended_next_node=live.node,
                rationale=live.message,
                governed_by="runtime state machine",
            )
        return StudioBrainView(session_id=sid, available=False)

    # ---------------------------------------------------------------- cache
    def cache(self, sid: str) -> StudioCacheView:
        """Cache metrics view (STU-CONV).

        Derived from persisted provider receipts (``cache_hit``); a dedicated
        cache-metrics sink (PR-000.3 optimizer) is not yet persisted, so the
        hit/miss view is evidence-backed by receipts only.
        """
        try:
            from opencontext_core.operating_model.receipts import RunReceiptStore

            receipts = RunReceiptStore(self._root).list_provider_receipts()
        except Exception:
            receipts = []
        if not receipts:
            return StudioCacheView(session_id=sid, available=False)
        hits = sum(1 for r in receipts if r.cache_hit)
        misses = len(receipts) - hits
        savings = sum(r.input_tokens for r in receipts if r.cache_hit)
        by_type: dict[str, int] = {}
        for r in receipts:
            if r.cache_hit:
                by_type[r.kind] = by_type.get(r.kind, 0) + 1
        return StudioCacheView(
            session_id=sid,
            available=True,
            hits=hits,
            misses=misses,
            hit_rate=round(hits / len(receipts), 4) if receipts else 0.0,
            token_savings=savings,
            by_type=by_type,
        )

    # ------------------------------------------------------------- learning
    def learning(self, sid: str) -> StudioLearningView:
        """Learning candidates view with benchmark evidence (STU-CONV)."""
        path = (
            resolve_workspace_path(self._root, StorageMode.local) / "learning" / "candidates.jsonl"
        )
        if not path.exists():
            return StudioLearningView(session_id=sid, available=False)
        candidates: list[StudioLearningCandidate] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = self._load_json_str(line)
            if not isinstance(data, dict):
                continue
            candidates.append(
                StudioLearningCandidate(
                    candidate_id=str(data.get("candidate_id", "")),
                    kind=str(data.get("kind", "")),
                    summary=str(data.get("summary", "")),
                    confidence=float(data.get("confidence", 0.0) or 0.0),
                    evidence=[str(e) for e in data.get("evidence", [])],
                )
            )
        return StudioLearningView(session_id=sid, available=bool(candidates), candidates=candidates)

    @staticmethod
    def _load_json_str(line: str) -> Any | None:
        try:
            return json.loads(line)
        except Exception:
            return None

    @staticmethod
    def _as_dict(section: Any) -> dict[str, Any]:
        """Normalize a config section (dict or pydantic model) to a plain dict."""
        if hasattr(section, "model_dump"):
            return dict(section.model_dump())
        return dict(section) if isinstance(section, dict) else {}

    @staticmethod
    def _str_list(value: Any) -> list[str]:
        """Coerce a JSON value to a ``list[str]`` (empty for non-sequences)."""
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return []

    # ---------------------------------------------------------------- config
    def config_view(self) -> StudioConfigView:
        """Config / profile + plugin read surface (SPEC-STU-014-10)."""
        try:
            from opencontext_core.config import (
                OpenContextConfig,
                default_config_data,
                find_config,
                load_config,
            )

            found = find_config(self._root)
            config = (
                load_config(found)
                if found is not None
                else OpenContextConfig.model_validate(default_config_data())
            )
        except Exception:
            return StudioConfigView(available=False)
        plugins_section = self._as_dict(getattr(config, "plugins", {}))
        installed = plugins_section.get("installed", plugins_section.get("enabled", []))
        plugins = [str(p) for p in installed] if isinstance(installed, list) else []
        studio_section = self._as_dict(getattr(config, "studio", {}))
        diagnostics: list[str] = []
        try:
            from opencontext_core.config_doctor import validate

            diagnostics = [str(getattr(d, "message", d)) for d in validate(self._root)]
        except Exception:
            diagnostics = []
        return StudioConfigView(
            available=True,
            profile=str(getattr(config, "profile", "")),
            studio_enabled=bool(studio_section.get("enabled", False)),
            plugins=plugins,
            diagnostics=diagnostics,
        )

    # ---------------------------------------------------- N2 surfacing (AVH-019)
    def task_history(self) -> StudioTaskHistoryView:
        """Runs that ended ``blocked``/``escalated``/``needs_*`` with their reason.

        Reads the OC Flow per-run ``state.json`` (B1/AVH-011) across every session
        so a no-op mutation run is surfaced honestly with its blocking reason.
        """
        base = resolve_workspace_path(self._root, StorageMode.local) / "sessions"
        tasks: list[StudioTaskStatus] = []
        if base.exists():
            for state_json in base.glob("*/runs/*/state.json"):
                data = self._load_json(state_json)
                if not isinstance(data, dict):
                    continue
                status = str(data.get("status", ""))
                if status not in _BLOCKED_STATUSES:
                    continue
                tasks.append(
                    StudioTaskStatus(
                        run_id=str(data.get("run_id", "")),
                        session_id=str(data.get("session_id", "")),
                        task=str(data.get("task", "")),
                        workflow=str(data.get("workflow", "")),
                        status=status,
                        reason=str(data.get("completion_reason", "")),
                        mutation_required=bool(data.get("mutation_required", False)),
                        updated_at=str(data.get("updated_at", "")),
                    )
                )
        tasks.sort(key=lambda t: t.updated_at, reverse=True)
        return StudioTaskHistoryView(
            available=bool(tasks),
            statuses=list(_BLOCKED_STATUSES),
            tasks=tasks,
        )

    def release_gate(self) -> StudioReleaseGateView:
        """Last ``release acceptance`` verdict (MET/FAILED/NOT_MEASURED + per-gate).

        Reads the persisted ``.opencontext/reports/acceptance.json`` snapshot; a
        missing snapshot degrades to ``available=False`` (no fabricated verdict).
        """
        path = resolve_workspace_path(self._root, StorageMode.local) / "reports" / "acceptance.json"
        data = self._load_json(path) if path.exists() else None
        if not isinstance(data, dict):
            return StudioReleaseGateView(available=False)
        gates = [
            StudioGateResult(
                gate=str(g.get("gate", "")),
                category=str(g.get("category", "")),
                status=str(g.get("status", "")),
                detail=str(g.get("detail", "")),
            )
            for g in data.get("gates", [])
            if isinstance(g, dict)
        ]
        return StudioReleaseGateView(
            available=True,
            ready=bool(data.get("ready", False)),
            met=int(data.get("met", 0) or 0),
            not_measured=int(data.get("not_measured", 0) or 0),
            failed=int(data.get("failed", 0) or 0),
            gates=gates,
        )

    def benchmark_coverage(self) -> StudioBenchmarkCoverageView:
        """Benchmark coverage from the last recorded run (``benchmark-history.json``)."""
        from opencontext_core.runtime_intelligence import telemetry_layout

        path = self._root / telemetry_layout.TELEMETRY_DIR / telemetry_layout.BENCHMARK_HISTORY_FILE
        history = self._load_json(path) if path.exists() else None
        if not isinstance(history, list) or not history:
            return StudioBenchmarkCoverageView(available=False)
        latest = history[-1]
        results = latest.get("results", []) if isinstance(latest, dict) else []
        per_suite: dict[str, StudioBenchmarkSuiteCoverage] = {}
        for res in results:
            if not isinstance(res, dict):
                continue
            suite = str(res.get("suite", ""))
            row = per_suite.setdefault(suite, StudioBenchmarkSuiteCoverage(suite=suite))
            row.total += 1
            if res.get("measured"):
                row.measured = True
                if res.get("success"):
                    row.success += 1
        suites = sorted(per_suite.values(), key=lambda s: s.suite)
        return StudioBenchmarkCoverageView(
            available=True,
            total_suites=len(suites),
            measured_suites=sum(1 for s in suites if s.measured),
            suites=suites,
        )
