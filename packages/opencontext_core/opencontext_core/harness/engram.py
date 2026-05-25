"""Engram memory adapter for harness run results.

Converts HarnessRunResult into structured memory entries that can be
persisted to Engram (semantic memory) for cross-session recall and
delta comparison across runs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from opencontext_core.harness.models import HarnessRunResult


class MemoryDelta:
    """A structured delta representing what changed in a harness run."""

    def __init__(
        self,
        run_id: str,
        workflow: str,
        task: str,
        status: str,
        token_deltas: dict[str, int] | None = None,
        gate_deltas: list[dict[str, Any]] | None = None,
        decision_deltas: list[dict[str, Any]] | None = None,
        artifact_deltas: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        timestamp: str | None = None,
    ) -> None:
        self.run_id = run_id
        self.workflow = workflow
        self.task = task
        self.status = status
        self.token_deltas = token_deltas or {}
        self.gate_deltas = gate_deltas or []
        self.decision_deltas = decision_deltas or []
        self.artifact_deltas = artifact_deltas or []
        self.warnings = warnings or []
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow": self.workflow,
            "task": self.task,
            "status": self.status,
            "token_deltas": self.token_deltas,
            "gate_deltas": self.gate_deltas,
            "decision_deltas": self.decision_deltas,
            "artifact_deltas": self.artifact_deltas,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
        }


class EngramMemoryAdapter:
    """Adapts harness run results into Engram-compatible memory entries.

    Produces structured deltas that capture what changed during a run:
    token consumption, gate evaluations, decisions made, and artifacts
    produced. These can be diffed across runs to detect regression or
    improvement.
    """

    def __init__(self, previous_result: HarnessRunResult | None = None) -> None:
        self._previous = previous_result

    def build_delta(self, current: HarnessRunResult) -> MemoryDelta:
        """Build a memory delta from the current run result.

        If a previous result was provided, the delta captures the diff
        between the two runs. Otherwise, all data is included as an
        initial snapshot.
        """
        token_deltas = self._compute_token_deltas(current)
        gate_deltas = self._compute_gate_deltas(current)
        decision_deltas = self._compute_decision_deltas(current)
        artifact_deltas = self._compute_artifact_deltas(current)

        return MemoryDelta(
            run_id=current.run_id,
            workflow=current.workflow,
            task=current.task,
            status=current.status.value,
            token_deltas=token_deltas,
            gate_deltas=gate_deltas,
            decision_deltas=decision_deltas,
            artifact_deltas=artifact_deltas,
            warnings=current.warnings,
        )

    def build_memory_entry(
        self, delta: MemoryDelta, project: str = "default"
    ) -> dict[str, Any]:
        """Build a structured memory entry suitable for engram storage.

        Returns a dict with the fields expected by engram's mem_save:
        title, content (structured), type, topic_key, and project.
        """
        content = self._format_memory_content(delta)
        return {
            "title": f"harness/{delta.workflow}/{delta.task}/{delta.run_id[:8]}",
            "content": content,
            "type": "harness_run",
            "topic_key": f"harness-runs/{delta.workflow}/{delta.task}",
            "project": project,
        }

    def _compute_token_deltas(
        self, current: HarnessRunResult
    ) -> dict[str, int]:
        deltas: dict[str, int] = {}
        for ledger in current.ledgers:
            phase = ledger.phase
            deltas[f"{phase}/used"] = ledger.used_tokens
            deltas[f"{phase}/budget"] = ledger.budget_tokens
            deltas[f"{phase}/remaining"] = ledger.remaining
            deltas[f"{phase}/exceeded"] = 1 if ledger.exceeded else 0

            if self._previous:
                prev_ledger = next(
                    (l for l in self._previous.ledgers if l.phase == phase),
                    None,
                )
                if prev_ledger:
                    delta = ledger.used_tokens - prev_ledger.used_tokens
                    deltas[f"{phase}/delta"] = delta

        # Totals
        total_used = sum(l.used_tokens for l in current.ledgers)
        deltas["total/used"] = total_used
        if self._previous:
            prev_total = sum(l.used_tokens for l in self._previous.ledgers)
            deltas["total/delta"] = total_used - prev_total

        return deltas

    def _compute_gate_deltas(
        self, current: HarnessRunResult
    ) -> list[dict[str, Any]]:
        gates = []
        for gate in current.gates:
            entry: dict[str, Any] = {
                "id": gate.id,
                "phase": gate.phase,
                "status": gate.status.value,
            }
            if gate.message:
                entry["message"] = gate.message
            gates.append(entry)
        return gates

    def _compute_decision_deltas(
        self, current: HarnessRunResult
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": d.id,
                "phase": d.phase,
                "status": d.status,
                "rationale": d.rationale,
            }
            for d in current.decisions
        ]

    def _compute_artifact_deltas(
        self, current: HarnessRunResult
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": a.id,
                "phase": a.phase,
                "kind": a.kind,
                "path": a.path,
            }
            for a in current.artifacts
        ]

    def _format_memory_content(self, delta: MemoryDelta) -> str:
        sections = [
            f"**Run**: {delta.run_id[:8]} ({delta.workflow}/{delta.task})",
            f"**Status**: {delta.status}",
            f"**Timestamp**: {delta.timestamp}",
        ]

        if delta.token_deltas:
            tok_lines = "\n".join(
                f"  - {k}: {v}" for k, v in delta.token_deltas.items()
            )
            sections.append(f"**Token Deltas**:\n{tok_lines}")

        if delta.gate_deltas:
            gate_lines = "\n".join(
                f"  - {g['id']}: {g['status']}"
                for g in delta.gate_deltas
            )
            sections.append(f"**Gate Evaluations**:\n{gate_lines}")

        if delta.decision_deltas:
            dec_lines = "\n".join(
                f"  - {d['id']}: {d['status']} ({d['rationale'][:80]})"
                for d in delta.decision_deltas
            )
            sections.append(f"**Decisions**:\n{dec_lines}")

        if delta.artifact_deltas:
            art_lines = "\n".join(
                f"  - {a['kind']}: {a['path']}"
                for a in delta.artifact_deltas
            )
            sections.append(f"**Artifacts**:\n{art_lines}")

        if delta.warnings:
            warn_lines = "\n".join(f"  - {w}" for w in delta.warnings)
            sections.append(f"**Warnings**:\n{warn_lines}")

        return "\n\n".join(sections)

    def serialize_delta(self, delta: MemoryDelta) -> str:
        """Serialize a memory delta to JSON for storage or transmission."""
        return json.dumps(delta.to_dict(), indent=2)

    @classmethod
    def deserialize_delta(cls, data: str) -> MemoryDelta:
        """Deserialize a memory delta from JSON."""
        raw = json.loads(data)
        return MemoryDelta(**raw)
