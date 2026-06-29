"""Runtime Brain — the advisory decision layer (PR-000.1).

The Brain *only decides*. It is structurally forbidden from side effects
(doc 59 §Brain restrictions): it MUST NOT modify files, invoke tools/commands,
write memory, skip/weaken harnesses, or govern transitions. This is enforced by
*capability*: :class:`RuntimeBrain` is constructed with **no** mutation/tool/
memory ports — only read ports (intelligence, KG, history) and a single
``record(decision)`` sink. ``decide(kind, context)`` returns exactly one
:class:`RuntimeDecision`; the deterministic State Machine governs.

Default strategies wrap today's scattered selectors (``ModelRoleRouter``,
``persona_for_phase``, ``SpecialistWorkflowRouter``, ``resolve_strategy`` /
``EconomyStrategy``) so behaviour is preserved while the choice becomes explicit
and recorded. The Brain is deterministic given its inputs: the same context
yields the same decision; adaptivity lives in the recorded ``inputs`` /
``confidence``, not in a hidden agent loop.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Protocol, runtime_checkable

from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.runtime.decisions import DecisionKind, RuntimeDecision
from opencontext_core.runtime.execution_strategy import resolve_strategy
from opencontext_core.runtime.ids import new_receipt_id

# A record sink: appends one decision and returns a log entry (typed Any to
# avoid importing decision_log here — it is the lower contract).
RecordSink = Callable[[RuntimeDecision], Any]


# --------------------------------------------------------------- read-only ports
@runtime_checkable
class IntelligencePort(Protocol):
    """Read-only cost/confidence feed (PR-011). Injected; never imported up."""

    def estimate(self, kind: str, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class KnowledgeGraphPort(Protocol):
    """Read-only KG lookup the Brain may consult when ranking alternatives."""

    def lookup(self, query: str) -> Any: ...


@runtime_checkable
class HistoryPort(Protocol):
    """Read-only access to prior decisions/results for this run."""

    def recent(self, run_id: str) -> Any: ...


@runtime_checkable
class RuntimeBrainPort(Protocol):
    """Recommend-only seam (PR-001). Returns ``None`` when it has no advice."""

    def recommend(
        self,
        *,
        run_id: str | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> RuntimeDecision | None: ...


class NullRuntimeBrain:
    """The default inert Brain: never recommends, never alters transitions."""

    def recommend(
        self,
        *,
        run_id: str | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> RuntimeDecision | None:
        return None


class RuntimeBrain:
    """Advisory Brain: produces one :class:`RuntimeDecision` per selection.

    Constructed with read ports + a record sink ONLY — there is, by design, no
    way to hand it a store, tool, harness, or memory writer (doc 59 §Brain
    restrictions). A guard test asserts this surface stays write-free.
    """

    def __init__(
        self,
        *,
        record: RecordSink | None = None,
        intelligence: IntelligencePort | None = None,
        kg: KnowledgeGraphPort | None = None,
        history: HistoryPort | None = None,
    ) -> None:
        self._record = record
        self._intelligence = intelligence
        self._kg = kg
        self._history = history
        # In-memory log of receipts emitted this session (read evidence, not a
        # durable store — persistence is PR-002's ReceiptStore).
        self.emitted_receipts: list[AgenticReceipt] = []

    # ------------------------------------------------------------------ decide
    def decide(self, kind: DecisionKind | str, context: Mapping[str, Any]) -> RuntimeDecision:
        """Return exactly one :class:`RuntimeDecision` for *kind*.

        Raises ``ValueError`` for an unsupported kind (the eight
        :class:`DecisionKind` values are all supported).
        """
        decision_kind = DecisionKind(str(kind))
        ctx = dict(context)
        strategy = self._STRATEGIES[decision_kind]
        chosen, alternatives, reason, confidence, inputs = strategy(self, ctx)

        decision = RuntimeDecision(
            kind=decision_kind.value,
            chosen=chosen,
            reason=reason,
            alternatives=alternatives,
            confidence=confidence,
            inputs=inputs,
            session_id=ctx.get("session_id"),
            run_id=ctx.get("run_id"),
            node_id=ctx.get("node_id"),
        )

        # Emit a receipt (reuse AgenticReceipt — no parallel model, RB-010) and
        # link it. Construction is in-memory only; no file is written.
        receipt = self._emit_receipt(decision)
        decision.receipt_id = receipt.trace_id

        if self._record is not None:
            self._record(decision)
        return decision

    def recommend(
        self,
        *,
        run_id: str | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> RuntimeDecision | None:
        """Recommend the next node (satisfies :class:`RuntimeBrainPort`).

        Advisory only — the State Machine still governs the transition.
        """
        ctx = dict(runtime_context or {})
        if run_id is not None:
            ctx.setdefault("run_id", run_id)
        return self.decide(DecisionKind.next_node, ctx)

    # ----------------------------------------------------------------- receipts
    def _emit_receipt(self, decision: RuntimeDecision) -> AgenticReceipt:
        """Build an :class:`AgenticReceipt` for a decision (no new receipt model)."""
        receipt = AgenticReceipt(
            run_id=decision.run_id or "advisory",
            change_id=decision.kind,
            flow_mode="advisory",
            openspec_mode="off",
            budget_mode="advisory",
            git_mode="none",
            status="recorded",
            trace_id=new_receipt_id(),
            task=f"decision:{decision.kind}",
            completed_phases=[decision.kind],
        )
        self.emitted_receipts.append(receipt)
        return receipt

    # --------------------------------------------------------------- strategies
    # Each returns (chosen, alternatives, reason, confidence, inputs). They wrap
    # today's selectors via local imports so the Brain has no hard module-load
    # dependency on the selection helpers (and no import cycle).
    def _decide_next_node(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        proposed = ctx.get("proposed_node") or ctx.get("next_node")
        if proposed:
            return (
                str(proposed),
                [],
                f"workflow graph proposes '{proposed}' after '{ctx.get('current_node')}'",
                0.9,
                {"current_node": ctx.get("current_node"), "source": "workflow_graph"},
            )
        task = str(ctx.get("task", "")).strip()
        if task:
            from opencontext_core.operating_model.quality import SpecialistWorkflowRouter

            workflow = SpecialistWorkflowRouter().route(task)
            return (
                workflow,
                [],
                f"no graph successor; routed task to specialist workflow '{workflow}'",
                0.5,
                {"task": task[:200], "source": "SpecialistWorkflowRouter"},
            )
        return ("", [], "no next node available (terminal or unknown)", 0.0, {})

    def _decide_persona(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        from opencontext_core.personas import persona_for_phase

        phase = str(ctx.get("phase", ""))
        persona = persona_for_phase(phase)
        chosen = persona.id if persona is not None else "none"
        reason = (
            f"persona '{chosen}' resolved for phase '{phase}'"
            if persona is not None
            else f"no persona mapped for phase '{phase}'"
        )
        return (chosen, [], reason, 0.8 if persona else 0.0, {"phase": phase})

    def _decide_provider(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        from opencontext_core.operating_model.performance import ModelRoleRouter

        role = str(ctx.get("role", "generate"))
        complexity = str(ctx.get("task_complexity", "standard"))
        router = ModelRoleRouter(
            roles=ctx.get("roles"),
            budget_manager=ctx.get("budget_manager"),
        )
        route = router.route_with_budget(role, complexity)
        chosen = f"{route['provider']}:{route['model']}"
        return (
            chosen,
            [],
            f"ModelRoleRouter selected {chosen} for role '{role}' (complexity '{complexity}')",
            0.7,
            {"role": role, "task_complexity": complexity},
        )

    def _decide_execution_profile(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        profile = str(ctx.get("profile", "balanced"))
        economy = ctx.get("economy")
        strategy = resolve_strategy(profile, economy=economy)
        reason = "; ".join(strategy.notes)
        return (
            strategy.profile,
            sorted(
                p
                for p in ("low-cost", "balanced", "enterprise", "research", "performance")
                if p != strategy.profile
            ),
            reason,
            0.9,
            {"execution_strategy": strategy.model_dump()},
        )

    def _decide_skill_bundle(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        bundle = str(ctx.get("skill_bundle", "default"))
        return (
            bundle,
            [],
            f"default skill bundle '{bundle}' (skill registry lands with PR-006)",
            0.4,
            {"phase": ctx.get("phase")},
        )

    def _decide_harnesses(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        harnesses = ctx.get("harnesses") or ["quality_gate"]
        chosen = ",".join(str(h) for h in harnesses)
        return (
            chosen,
            [],
            f"harnesses '{chosen}' (Brain may strengthen, never weaken; registry: PR-006/007)",
            0.5,
            {"harnesses": list(harnesses)},
        )

    def _decide_context_strategy(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        strategy = str(ctx.get("context_strategy", "verified_minimal"))
        return (
            strategy,
            ["full", "compressed"],
            f"context strategy '{strategy}' (full Context API resolution lands with PR-010)",
            0.5,
            {},
        )

    def _decide_retry_policy(
        self, ctx: Mapping[str, Any]
    ) -> tuple[str, list[str], str, float, dict[str, Any]]:
        profile = str(ctx.get("profile", "balanced"))
        strategy = resolve_strategy(profile)
        chosen = f"retry_budget={strategy.retry_budget}"
        return (
            chosen,
            [],
            f"retry/diagnosis policy from profile '{strategy.profile}': {chosen}",
            0.7,
            {"retry_budget": strategy.retry_budget, "profile": strategy.profile},
        )

    # Strategy dispatch table — covers all eight DecisionKind values.
    _STRATEGIES: ClassVar[
        dict[
            DecisionKind,
            Callable[
                [RuntimeBrain, Mapping[str, Any]],
                tuple[str, list[str], str, float, dict[str, Any]],
            ],
        ]
    ] = {
        DecisionKind.next_node: _decide_next_node,
        DecisionKind.persona: _decide_persona,
        DecisionKind.provider: _decide_provider,
        DecisionKind.execution_profile: _decide_execution_profile,
        DecisionKind.skill_bundle: _decide_skill_bundle,
        DecisionKind.harnesses: _decide_harnesses,
        DecisionKind.context_strategy: _decide_context_strategy,
        DecisionKind.retry_policy: _decide_retry_policy,
    }
