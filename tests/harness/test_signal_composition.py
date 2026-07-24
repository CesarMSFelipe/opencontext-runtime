"""Integration: the six-part wiring COMPOSES — all signals coexist per spine.

Each slice of the phase-memory-wiring program was proven in isolation:

* ``test_phase_memory_enforcement.py`` — rodaja 1: recalled memory reaches the
  middle phases' executor context;
* ``test_phase_kg_context.py``         — rodaja 3: a fresh, budget-capped,
  KG-grounded pack reaches the executor context;
* ``test_minimal_diff_instruction.py`` — rodaja 4: the minimal-diff sentinel
  reaches BOTH code-gen spines;
* ``test_tdd_posture_codegen.py`` / ``test_oc_flow_tdd_posture.py`` — rodaja 5:
  the strict-TDD posture line reaches BOTH code-gen spines.

Those tests each exercise ONE seam. This file proves they WORK TOGETHER: that a
STRICT-TDD ``apply`` code-gen context, assembled in the HARNESS with both memory
recall and KG available, carries ALL FOUR signals in the SAME model-facing prompt
— none clobbering another — and stays within the apply phase's token budget. Then
the equivalent for the OC Flow ``mutate`` spine (minimal-diff + strict-TDD posture
together — the two RUNTIME signals that reach the ``mutate`` prompt text; KG /
memory travel via the ContextEnvelope upstream of ``mutate``, not inside its
prompt string, so they are asserted at the harness spine where they DO converge).

All fakes are reused from the isolation tests' shapes (a recording memory store,
a recording KG runtime, a capturing gateway/delegate). Model-free and
tmp-isolated: no network round-trip, no real index.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import opencontext_core.harness.phases as phases_mod
from opencontext_core.agents.executor import (
    MINIMAL_DIFF_SENTINEL,
    generate_apply_edits,
)
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.harness.phases import _fold_apply_kg_context
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.memory.phase_gateway import RecallResult
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryLifecycle,
    MemoryRecord,
)
from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow.models import ContextEnvelope, TaskContract
from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
from opencontext_core.paths.execution_state import runs_root

# --- the four signal sentinels ------------------------------------------------

MEM_SENTINEL = "RECALLED-MEMORY-SENTINEL bcrypt rule"  # rodaja 1
KG_SENTINEL = "KG-FRESH-CONTEXT-SENTINEL authenticate bcrypt"  # rodaja 3
MINIMAL_DIFF = MINIMAL_DIFF_SENTINEL  # rodaja 4 — "Produce the SMALLEST change…"
TDD_SENTINEL = "TDD strict"  # rodaja 5 — "TDD strict…"


# --- fakes (same shapes the isolation tests use) ------------------------------


@dataclass
class _FakeItem:
    source: str
    content: str


@dataclass
class _FakePack:
    included: list[_FakeItem]
    used_tokens: int = 40


class _RecordingRuntime:
    """Records build_context_pack(query, budget); returns a canned KG pack.

    Mirrors the OpenContextRuntime surface the middle/apply KG fold uses so the
    KG sentinel flows into ``state.context_pack`` without a real index.
    """

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def build_context_pack(self, query: str, max_tokens: int | None = None, **_k: Any) -> _FakePack:
        self.calls.append((query, max_tokens))
        return _FakePack(included=[_FakeItem(source="auth.py", content=KG_SENTINEL)])

    def index_project(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover - safety
        raise AssertionError("apply must not re-index")


class _CapturingGateway:
    """Records the request whose prompt we assert on; returns an empty edit set."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def generate(self, request: Any) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            content="[]", provider="mock", model="stub", input_tokens=1, output_tokens=1
        )


def _canned_record(text: str = MEM_SENTINEL) -> MemoryRecord:
    """A trusted (active) SEMANTIC record the recall path returns for the apply phase.

    ``lifecycle=ACTIVE`` + ``status=ACTIVE`` is what ``PhaseMemoryGateway._is_trusted``
    requires, so the runner's real recall partitions it into ``trusted`` and
    ``RecallResult.render`` emits it under the "Trusted" heading.
    """
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id="canned-semantic",
        layer=MemoryLayer.SEMANTIC,
        key="canned:0",
        content=text,
        lifecycle=MemoryLifecycle.ACTIVE,
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
    )


def _recalled_memory_block(text: str = MEM_SENTINEL) -> str:
    """Render a recalled-memory block exactly as PhaseMemoryGateway.recall would.

    Uses the real ``RecallResult.render`` so the block the runner folds into the
    apply-codegen ``context`` is byte-identical to production, not a hand-rolled
    approximation.
    """
    return RecallResult(trusted=[_canned_record(text)]).render()


class _RecordingMemoryStore:
    """A minimal AgentMemoryStore-shaped stub the runner's PhaseMemoryGateway drives.

    Returns the canned record ONLY for the SEMANTIC layer (apply's first read layer),
    exercising the REAL recall path: the runner calls ``recall("apply", task)`` which
    calls ``store.search(query, scope=layer, limit=...)`` per declared read layer. The
    record's content is what must ultimately reach the apply-codegen prompt — proving
    the recall→prompt seam, not merely that the store was searched.
    """

    def __init__(self, record: MemoryRecord) -> None:
        self._record = record
        self.searches: list[tuple[str, Any]] = []

    def search(
        self, query: str, *, scope: Any = None, limit: int = 5, **_k: Any
    ) -> list[MemoryRecord]:
        self.searches.append((query, scope))
        return [self._record] if scope == MemoryLayer.SEMANTIC else []


def _seed_tasks(state: Any) -> None:
    """Seed tasks.json so ``_fold_apply_kg_context`` derives a real query."""
    run_dir = runs_root(state.root) / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tasks.json").write_text(
        json.dumps(
            [
                {
                    "id": "task-1",
                    "description": "Implement bcrypt in authenticate",
                    "file_paths": ["auth.py"],
                }
            ]
        ),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# HARNESS apply code-gen — the four signals converge in ONE prompt.
# --------------------------------------------------------------------------- #


def test_harness_apply_context_composes_all_four_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build a STRICT-TDD apply code-gen context in the harness with BOTH memory
    recall (rodaja 1) and KG (rodaja 3) available; the assembled prompt must carry
    ALL FOUR signals TOGETHER, none clobbering another, within the apply budget.

    This drives the REAL runner seams end to end for the apply-codegen prompt:

    * rodaja 1 — the recalled-memory block (rendered by ``RecallResult.render``,
      as the runner's ``PhaseMemoryGateway`` recall produces) is seeded into
      ``state.context_pack`` (the field ``_generate_apply_edits`` reads);
    * rodaja 3 — ``_fold_apply_kg_context`` folds a fresh KG pack (from the fake
      runtime) into that same ``state.context_pack``;
    * rodaja 4 / 5 — ``_generate_apply_edits`` composes the minimal-diff signal
      and, because ``tdd_mode == 'strict'``, the strict-TDD posture line into the
      final prompt alongside the task + verified pack.
    """
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")

    runtime = _RecordingRuntime()
    monkeypatch.setattr(phases_mod, "OpenContextRuntime", lambda *a, **k: runtime)

    gateway = _CapturingGateway()
    runner = HarnessRunner(root=tmp_path)
    # Force a real gateway/provider so the codegen path actually fires, and a strict
    # TDD posture so rodaja 5 emits its line (the harness conftest defaults tdd=off).
    monkeypatch.setattr(runner, "_resolve_gateway", lambda: (gateway, "anthropic", "claude"))
    monkeypatch.setattr(runner, "_harness_governance", lambda: ("strict", False))

    state = runner.create_run("sdd", "improve authenticate password hashing")
    _seed_tasks(state)

    # rodaja 1: seed recalled memory into context_pack (what the runner's gateway
    # recall folds in before apply), tagged with an explore base so we can prove
    # composition preserves the base too.
    state.context_pack = f"### explore base\nEXPLORE-BASE-MARKER\n\n{_recalled_memory_block()}"

    # rodaja 3: fold a fresh, budget-capped KG pack derived from the task list.
    apply_cfg = runner.config.phases["apply"]
    _fold_apply_kg_context(state, apply_cfg.budget_tokens)

    # rodaja 4 + 5: compose the apply-codegen prompt exactly as the runner does.
    state.apply_edits = runner._generate_apply_edits(state)

    assert gateway.calls, "apply codegen did not reach the gateway"
    prompt = gateway.calls[0].prompt

    # ALL FOUR signals are present in the SAME assembled prompt — together.
    assert MEM_SENTINEL in prompt, "rodaja 1 (recalled memory) missing from apply prompt"
    assert KG_SENTINEL in prompt, "rodaja 3 (fresh KG context) missing from apply prompt"
    assert MINIMAL_DIFF in prompt, "rodaja 4 (minimal-diff sentinel) missing from apply prompt"
    assert TDD_SENTINEL in prompt, "rodaja 5 (strict-TDD posture) missing from apply prompt"

    # None clobbered another: the explore base and the task survive alongside them.
    assert "EXPLORE-BASE-MARKER" in prompt, "composing the signals dropped the explore base"
    assert "improve authenticate password hashing" in prompt, "the task was clobbered"

    # The strict-TDD line is the RED-unknown half (no failing test proven yet here).
    assert "failing test" in prompt.lower()

    # Bounded by the apply phase token budget — the composition stays economical.
    assert estimate_tokens(prompt) <= apply_cfg.budget_tokens, (
        f"composed apply prompt {estimate_tokens(prompt)} tok exceeds the apply "
        f"budget {apply_cfg.budget_tokens}"
    )


def test_harness_apply_signal_order_is_deterministic(tmp_path: Path) -> None:
    """The four signals compose in a stable, readable order in the apply prompt.

    Minimal-diff frames the request first, then the strict-TDD posture, then the
    task, then the verified pack carrying recalled memory + KG. This asserts the
    ADDITIVE composition (rodaja 4 → 5 → task → 1+3), so a future regression that
    reorders or drops a signal is caught, not just its bare presence.
    """
    gateway = _CapturingGateway()
    # The pack blob is what the runner hands over as context["context"]: it already
    # contains the recalled memory (rodaja 1) + the KG block (rodaja 3), composed
    # upstream by the runner's recall + _fold_apply_kg_context.
    pack = (
        "### explore base\nEXPLORE-BASE-MARKER\n\n"
        f"{_recalled_memory_block()}\n\n"
        f"### fresh apply context (KG-grounded, budget 12000)\n### auth.py\n{KG_SENTINEL}"
    )
    context = {
        "task": "improve authenticate password hashing",
        "context": pack,
        "tdd_mode": "strict",
        "tdd_red_proven": False,
    }

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    prompt = gateway.calls[0].prompt
    i_min = prompt.index(MINIMAL_DIFF)
    i_tdd = prompt.index(TDD_SENTINEL)
    i_task = prompt.index("improve authenticate password hashing")
    i_mem = prompt.index(MEM_SENTINEL)
    i_kg = prompt.index(KG_SENTINEL)

    # Every signal present, and composed in the intended additive order.
    assert i_min < i_tdd < i_task < i_mem, (
        "apply prompt signal order regressed (expected minimal-diff → TDD → task → memory)"
    )
    # KG and memory both live in the verified-context block (after the task).
    assert i_task < i_kg
    assert "## Verified context" in prompt


def test_harness_apply_red_proven_picks_minimal_code_half_still_composed(
    tmp_path: Path,
) -> None:
    """With RED already proven, the strict line flips to "make it pass" — and the
    other three signals still compose alongside it (nothing is dropped)."""
    gateway = _CapturingGateway()
    pack = f"{_recalled_memory_block()}\n\n### auth.py\n{KG_SENTINEL}"
    context = {
        "task": "improve authenticate password hashing",
        "context": pack,
        "tdd_mode": "strict",
        "tdd_red_proven": True,
    }

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    prompt = gateway.calls[0].prompt
    lowered = prompt.lower()
    # The RED-proven half of the strict line.
    assert "make it pass" in lowered or "minimal code" in lowered
    # And the full quartet still coexists.
    assert MEM_SENTINEL in prompt
    assert KG_SENTINEL in prompt
    assert MINIMAL_DIFF in prompt
    assert TDD_SENTINEL in prompt


# --------------------------------------------------------------------------- #
# HARNESS apply — the REAL recall→prompt seam (HIGH 1 regression guard).
#
# The tests above seed recalled memory into ``state.context_pack`` DIRECTLY, which
# bypasses the runner's actual recall path (recall writes ``state.phase_memory``,
# NOT ``state.context_pack``) — that blind spot let the recalled memory silently
# NEVER reach the apply-codegen prompt while every "composition" test stayed green.
# This test drives the REAL path end to end: seed a record in the INJECTED store,
# let the runner's PhaseMemoryGateway recall it for the apply phase onto
# ``state.phase_memory``, and assert the recalled content lands in the ACTUAL
# ``generate_apply_edits`` prompt.
# --------------------------------------------------------------------------- #


def test_harness_apply_recalls_memory_into_codegen_prompt_via_real_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner's REAL recall must land the recalled memory in the apply prompt.

    RED before HIGH 1: ``_generate_apply_edits`` builds its ``context`` from
    ``state.context_pack`` only and never reads ``state.phase_memory``, so the
    memory the gateway recalled into ``state.phase_memory`` is DROPPED before it can
    reach the model. GREEN after HIGH 1 folds ``state.phase_memory`` into the
    apply-codegen context.
    """
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")

    gateway = _CapturingGateway()
    store = _RecordingMemoryStore(_canned_record())
    # Inject the store so the runner builds its PhaseMemoryGateway around it — the
    # recall runs for real (no monkeypatching of state.phase_memory / context_pack).
    runner = HarnessRunner(root=tmp_path, memory_store=store)
    monkeypatch.setattr(runner, "_resolve_gateway", lambda: (gateway, "anthropic", "claude"))
    monkeypatch.setattr(runner, "_harness_governance", lambda: ("strict", False))

    state = runner.create_run("sdd", "improve authenticate password hashing")
    _seed_tasks(state)
    # The explore pack is what context_pack carries into apply — memory is NOT here;
    # it must arrive via the recall→phase_memory seam, not this field.
    state.context_pack = "### explore base\nEXPLORE-BASE-MARKER"

    # Drive the runner's REAL recall for the apply phase (the same call the run loop
    # makes at ~955), populating state.phase_memory from the injected store.
    recall = runner._phase_gateway.recall("apply", state.task)
    state.phase_memory = recall.render()

    # Sanity: the real recall actually searched the store AND surfaced the record,
    # so a failure below is a DROP in codegen, not an empty recall.
    assert store.searches, "the runner's recall never searched the injected store"
    assert MEM_SENTINEL in state.phase_memory, "recall did not surface the seeded memory"

    state.apply_edits = runner._generate_apply_edits(state)

    assert gateway.calls, "apply codegen did not reach the gateway"
    prompt = gateway.calls[0].prompt
    # THE assertion: recalled memory reaches the real model-facing apply prompt.
    assert MEM_SENTINEL in prompt, (
        "recalled memory (state.phase_memory) was DROPPED from the apply-codegen prompt "
        "— it must be folded into _generate_apply_edits' context (HIGH 1)"
    )
    # The other signals still compose alongside it (no regression).
    assert MINIMAL_DIFF in prompt
    assert TDD_SENTINEL in prompt
    assert "EXPLORE-BASE-MARKER" in prompt
    assert "improve authenticate password hashing" in prompt


# --------------------------------------------------------------------------- #
# OC Flow mutate — the RUNTIME signals converge in ONE prompt.
# --------------------------------------------------------------------------- #


def test_oc_flow_mutate_composes_minimal_diff_and_tdd(tmp_path: Path) -> None:
    """The OC Flow ``mutate`` prompt carries minimal-diff (rodaja 4) AND the
    strict-TDD posture (rodaja 5) TOGETHER, additively with the contract scope.

    OC Flow does not use the SDD Builder persona, so both are threaded as RUNTIME
    instructions into the ``mutate`` prompt. KG-grounding and recalled memory reach
    OC Flow via the ContextEnvelope built upstream (gather_context / planning), not
    inside the ``mutate`` prompt string — so the four-way convergence is asserted on
    the harness spine above; here we assert the two signals that DO share the mutate
    prompt coexist without clobbering the task.
    """
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(
        gateway=gateway, root=tmp_path, provider="mock", tdd_mode="strict"
    )
    contract = TaskContract(
        scope="Fix the failing add() test",
        acceptance_criteria=["add returns the sum"],
        verification_plan=["run the add() test"],
    )

    executor.mutate(contract, ContextEnvelope(task="Fix the failing add() test"))

    assert gateway.calls, "mutate did not reach the gateway"
    prompt = gateway.calls[0].prompt

    # Both runtime signals coexist in the SAME mutate prompt.
    assert MINIMAL_DIFF in prompt, "rodaja 4 (minimal-diff) missing from mutate prompt"
    assert TDD_SENTINEL in prompt, "rodaja 5 (strict-TDD posture) missing from mutate prompt"
    # Additive: the contract scope + acceptance survive alongside them.
    assert "Fix the failing add() test" in prompt
    assert "add returns the sum" in prompt

    # Order is deterministic: minimal-diff frames, then the TDD line, then the task.
    assert (
        prompt.index(MINIMAL_DIFF)
        < prompt.index(TDD_SENTINEL)
        < prompt.index("Fix the failing add() test")
    )


def test_oc_flow_mutate_red_proven_composes_minimal_code_half(tmp_path: Path) -> None:
    """RED proven (non-zero pre-mutation exit) → the strict line's "make it pass"
    half composes alongside the minimal-diff signal in the mutate prompt."""
    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(
        gateway=gateway,
        root=tmp_path,
        provider="mock",
        tdd_mode="strict",
        tdd_red_exit_code=1,
    )
    contract = TaskContract(
        scope="Fix the failing add() test",
        acceptance_criteria=["add returns the sum"],
        verification_plan=["run the add() test"],
    )

    executor.mutate(contract, ContextEnvelope(task="Fix the failing add() test"))

    prompt = gateway.calls[0].prompt
    assert MINIMAL_DIFF in prompt
    assert TDD_SENTINEL in prompt
    assert "make it pass" in prompt.lower() or "minimal code" in prompt.lower()


# --------------------------------------------------------------------------- #
# OC Flow mutate — the REAL memory→prompt seam (HIGH 2 regression guard).
#
# ``_fold_phase_memory`` folds ``ctx.phase_memory`` into the envelope as a
# ``source="memory"`` item, but ``mutate`` built its prompt from ONLY the contract
# scope + acceptance (envelope unused), so the recalled memory never reached the OC
# Flow model. This test drives the REAL fold and asserts the folded memory lands in
# the ACTUAL mutate prompt.
# --------------------------------------------------------------------------- #


def test_oc_flow_mutate_renders_recalled_memory_into_prompt(tmp_path: Path) -> None:
    """The recalled memory folded onto the envelope must reach the mutate prompt.

    RED before HIGH 2: ``mutate`` ignores the ContextEnvelope entirely, so the
    ``source="memory"`` item ``_fold_phase_memory`` folds in is DROPPED before the
    model. GREEN after HIGH 2 renders the recalled memory into the mutate prompt
    string alongside the minimal-diff + TDD lines.
    """
    from opencontext_core.oc_flow.nodes import _fold_phase_memory

    gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(
        gateway=gateway, root=tmp_path, provider="mock", tdd_mode="strict"
    )
    contract = TaskContract(
        scope="Fix the failing add() test",
        acceptance_criteria=["add returns the sum"],
        verification_plan=["run the add() test"],
    )

    # Build the envelope through the REAL fold: a ctx-shaped object whose
    # phase_memory the fold turns into a source="memory" envelope item, exactly as
    # node_mutate does at ~1224 before calling executor.mutate.
    ctx = SimpleNamespace(
        phase_memory=_recalled_memory_block(),
        envelope=ContextEnvelope(task="Fix the failing add() test"),
    )
    _fold_phase_memory(ctx)
    assert any(i.source == "memory" for i in ctx.envelope.items), (
        "the real fold did not add a source='memory' item to the envelope"
    )

    executor.mutate(contract, ctx.envelope)

    assert gateway.calls, "mutate did not reach the gateway"
    prompt = gateway.calls[0].prompt
    # THE assertion: the recalled memory reaches the real model-facing mutate prompt.
    assert MEM_SENTINEL in prompt, (
        "recalled memory (envelope source='memory' item) was DROPPED from the mutate "
        "prompt — it must be rendered into the mutate prompt string (HIGH 2)"
    )
    # The runtime signals + task still compose alongside it (no regression).
    assert MINIMAL_DIFF in prompt
    assert TDD_SENTINEL in prompt
    assert "Fix the failing add() test" in prompt


# --------------------------------------------------------------------------- #
# Both-spines sanity — neither best-effort path crashes; providers resolve.
# --------------------------------------------------------------------------- #


def test_both_spines_reach_executor_without_the_best_effort_paths_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A harness apply codegen AND an OC Flow mutate each reach their executor with
    the composed context, and the best-effort memory/KG folds never raise."""
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")

    # --- harness spine: real seams, capturing gateway ---
    runtime = _RecordingRuntime()
    monkeypatch.setattr(phases_mod, "OpenContextRuntime", lambda *a, **k: runtime)
    h_gateway = _CapturingGateway()
    runner = HarnessRunner(root=tmp_path)
    monkeypatch.setattr(runner, "_resolve_gateway", lambda: (h_gateway, "anthropic", "claude"))
    monkeypatch.setattr(runner, "_harness_governance", lambda: ("strict", False))
    state = runner.create_run("sdd", "improve authenticate password hashing")
    _seed_tasks(state)
    state.context_pack = _recalled_memory_block()
    # Best-effort KG fold must not raise even though the runtime is a fake.
    _fold_apply_kg_context(state, runner.config.phases["apply"].budget_tokens)
    state.apply_edits = runner._generate_apply_edits(state)
    assert h_gateway.calls, "harness spine never reached the executor gateway"

    # --- OC Flow spine: mutate reaches the gateway with the runtime signals ---
    f_gateway = _CapturingGateway()
    executor = ProviderBackedNodeExecutor(
        gateway=f_gateway, root=tmp_path, provider="mock", tdd_mode="strict"
    )
    executor.mutate(
        TaskContract(
            scope="Fix the failing add() test",
            acceptance_criteria=["add returns the sum"],
            verification_plan=["run the add() test"],
        ),
        ContextEnvelope(task="Fix the failing add() test"),
    )
    assert f_gateway.calls, "OC Flow spine never reached the executor gateway"


def test_fold_apply_kg_context_is_best_effort_when_runtime_boom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the KG runtime raises, the apply KG fold leaves context_pack untouched and
    never blocks the apply-codegen path (the composition degrades, does not crash)."""

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("no index")

    monkeypatch.setattr(phases_mod, "OpenContextRuntime", _boom)

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "improve authenticate password hashing")
    _seed_tasks(state)
    original = _recalled_memory_block()
    state.context_pack = original

    _fold_apply_kg_context(state, runner.config.phases["apply"].budget_tokens)

    # Memory (rodaja 1) survives; the KG fold degraded silently (rodaja 3 best-effort).
    assert state.context_pack == original
    assert MEM_SENTINEL in state.context_pack


@pytest.mark.parametrize("provider", ["local", "auto"])
def test_memory_resolves_for_local_and_auto(provider: str, tmp_path: Path) -> None:
    """The memory store resolves to a usable store for provider ``local`` AND
    ``auto`` (auto degrades to local when no co-resident Engram is present), and a
    round-trip search/write does not raise — the recall spine both spines share."""
    from types import SimpleNamespace

    from opencontext_core.backends.factory import BackendFactory
    from opencontext_core.config import SecurityMode
    from opencontext_core.memory.agent import AgentMemoryStore

    cfg = SimpleNamespace(
        memory=SimpleNamespace(enabled=True, provider=provider),
        security=SimpleNamespace(mode=SecurityMode.DEVELOPER),
    )
    store = BackendFactory.create_memory_store(cfg, tmp_path)

    # A real, usable AgentMemoryStore (auto with no Engram degrades to local).
    assert isinstance(store, AgentMemoryStore)
    # Exercise the port surface the PhaseMemoryGateway drives — must not raise.
    assert store.search("authenticate") == [] or isinstance(store.search("authenticate"), list)


def test_quickstart_defaults_yields_complete_config() -> None:
    """The onboarding quick-start yields a complete config: template, security,
    TDD, agents, and a memory provider that includes co-resident Engram (auto)."""
    from opencontext_core.onboarding.wizard import InteractiveOnboardingWizard

    defaults = InteractiveOnboardingWizard.quickstart_defaults()

    # Every decision the wizard would prompt for has a recommended value.
    for key in ("template", "security_mode", "tdd", "agents", "memory_provider"):
        assert key in defaults, f"quick-start config missing {key!r}"
        assert defaults[key] is not None, f"quick-start config has null {key!r}"

    # Memory defaults to 'auto' so a co-resident Engram is used when present.
    assert defaults["memory_provider"] == "auto"
    # Security is a valid mode; agents is a concrete (possibly-detected) list.
    assert defaults["security_mode"] in InteractiveOnboardingWizard.security_mode_choices()
    assert isinstance(defaults["agents"], list)
