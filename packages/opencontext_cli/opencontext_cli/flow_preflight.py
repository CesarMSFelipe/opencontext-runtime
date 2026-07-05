"""Guided preflight briefings for flow-executing commands.

Before a flow executes (``opencontext run``, ``opencontext oc-new start``) the
CLI renders a branded briefing: HOW the process will work (nodes/phases and
pause policy), WHAT it will produce (the evidence spine of artifacts), and WHAT
OPTIONS the user has — then asks before executing.

Every option follows the config-TUI detail-card format (Current / Effect /
Recommended / Risk / CLI) so the whole product explains choices the same way.

Gating: the preflight only appears on an interactive TTY. ``--json``, ``--yes``
and ``--non-interactive`` skip it, and non-TTY sessions (scripts, CI, pipes)
behave exactly as before — no prompt, direct execution, zero breakage.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencontext_core import prompts
from opencontext_core.dx.console_styles import console

__all__ = [
    "DetailCard",
    "OcNewDecision",
    "RunDecision",
    "is_interactive",
    "oc_new_preflight",
    "render_gate_panel",
    "run_preflight",
]


# --------------------------------------------------------------------- gating
def _is_tty() -> bool:
    """True when both stdin and stdout are real TTYs (mirrors prompts._is_tty)."""
    return bool(getattr(sys.stdin, "isatty", lambda: False)()) and bool(
        getattr(sys.stdout, "isatty", lambda: False)()
    )


def is_interactive(args: Any) -> bool:
    """Whether the preflight should run for this invocation.

    Skips for ``--json`` (machine output must stay pure), ``--yes`` /
    ``--non-interactive`` (explicit opt-outs), and any non-TTY session.
    """
    if getattr(args, "json", False) or getattr(args, "json_out", False):
        return False
    if getattr(args, "yes", False) or getattr(args, "non_interactive", False):
        return False
    return _is_tty()


# --------------------------------------------------------------- detail cards
@dataclass(frozen=True)
class DetailCard:
    """Config-TUI style detail card: one block per option, five fixed lines."""

    current: str
    effect: str
    recommended: str
    risk: str
    cli: str

    def lines(self) -> list[str]:
        return [
            f"Current: {self.current}",
            f"Effect: {self.effect}",
            f"Recommended: {self.recommended}",
            f"Risk / note: {self.risk}",
            f"CLI: {self.cli}",
        ]


def _render_option_cards(title: str, cards: list[tuple[str, DetailCard]]) -> None:
    """Render labelled detail cards in one branded panel."""
    blocks = []
    for label, card in cards:
        body = "\n".join(f"  {line}" for line in card.lines())
        blocks.append(f"{label}\n{body}")
    console.panel("\n\n".join(blocks), title=title)


# ------------------------------------------------------------- run preflight
@dataclass(frozen=True)
class RunDecision:
    """Outcome of the run preflight: whether to proceed and with which knobs."""

    proceed: bool
    workflow: str
    lane: str


def _resolve_workflow(task: str, workflow: str) -> tuple[str, str]:
    """Resolve the workflow that will actually execute, with the selection reason."""
    if workflow == "auto":
        try:
            from opencontext_core.context.planning.workflow_selector import select_workflow

            selection = select_workflow(task)
            return selection.workflow, f"auto selection: {selection.reason}"
        except Exception:
            return "oc-flow", "auto selection unavailable; defaulting to oc-flow"
    return workflow, f"explicitly requested via --workflow {workflow}"


def _workflow_definition(workflow_id: str) -> Any | None:
    """Load the declarative workflow definition, or None when unavailable."""
    try:
        from opencontext_core.oc_flow.definition import oc_flow_registry

        registry = oc_flow_registry()
        if registry.has(workflow_id):
            return registry.get(workflow_id)
    except Exception:
        pass
    return None


def _subsystem_lines(root: Path) -> list[str]:
    """Honest memory / KG / compression status for this run, from project config."""
    try:
        from opencontext_core.config import load_config_or_defaults
        from opencontext_core.config_resolver import resolve_config_path

        cfg = load_config_or_defaults(resolve_config_path(root), auto_detect=False)
        memory = cfg.memory
        kg = cfg.knowledge_graph
        compression = cfg.context.compression
        runtime = cfg.runtime
        kg_suffix = " (v2 gather path)" if getattr(runtime, "kg_v2_enabled", False) else ""
        engine_suffix = (
            " via context engine" if getattr(runtime, "context_engine_enabled", False) else ""
        )
        return [
            f"Memory          : {'on' if memory.enabled else 'off'} "
            f"(mode: {memory.mode.value}) — learnings land in the memory delta",
            f"Knowledge graph : {'on' if kg.enabled else 'off'}{kg_suffix} "
            "— grounds context gathering in indexed symbols",
            f"Compression     : {'on' if compression.enabled else 'off'}{engine_suffix} "
            "— packs context instead of dumping raw files",
        ]
    except Exception:
        return [
            "Memory          : defaults (project config unavailable)",
            "Knowledge graph : defaults (project config unavailable)",
            "Compression     : defaults (project config unavailable)",
        ]


def _estimate_lines(task: str, workflow: str, lane: str, root: Path) -> list[str]:
    """Surface the pre-run cost estimate (previously stderr-only) in the briefing."""
    try:
        from opencontext_core.runtime_intelligence.cost import CostEngine

        estimate = CostEngine().estimate(task, workflow, lane, root=root)
        return [
            f"Tokens     : ~{estimate.estimated_input_tokens} in / "
            f"~{estimate.estimated_output_tokens} out",
            f"Tool calls : ~{estimate.estimated_tool_calls}",
            f"Duration   : ~{estimate.estimated_duration_s}s "
            f"(confidence {estimate.confidence:.0%})",
        ]
    except Exception:
        return ["Cost estimate unavailable for this task."]


def _render_run_briefing(
    task: str,
    workflow: str,
    resolved_workflow: str,
    reason: str,
    lane: str,
    profile: str,
    root: Path,
) -> None:
    console.header("Run Preflight")

    plan_lines = [
        f"Task     : {task}",
        f"Workflow : {resolved_workflow} — {reason}",
        f"Lane     : {lane} (context depth, diagnosis budget, strictness)",
        f"Profile  : {profile}",
    ]
    console.panel("\n".join(plan_lines), title="Execution plan")

    definition = _workflow_definition(resolved_workflow)
    if definition is not None:
        sequence = " → ".join(definition.nodes)
        how_lines = [f"Nodes : {sequence}"]
        if resolved_workflow == "oc-flow":
            how_lines.append(
                "Note  : diagnose and escalation run only when local inspection fails."
            )
        console.panel("\n".join(how_lines), title="How it will run")

        artifacts: list[str] = []
        for node in definition.nodes.values():
            for output in getattr(node, "required_outputs", []):
                if output not in artifacts:
                    artifacts.append(output)
        if artifacts:
            console.panel(
                "\n".join(f"- {artifact}" for artifact in artifacts),
                title="It will produce (evidence spine)",
            )

    gate_lines = [
        "Policy     : tool calls run under the tool permission policy "
        "(writes are approval-gated by default)",
        "Inspection : the changed scope is inspected (tests / lint / types) "
        "before the run can complete",
        "Completion : the run only finishes through the completion gate; "
        "every step leaves receipts",
    ]
    console.panel("\n".join(gate_lines), title="Gates that will judge this run")

    estimate = "\n".join(_estimate_lines(task, resolved_workflow, lane, root))
    console.panel(estimate, title="Cost estimate")
    console.panel("\n".join(_subsystem_lines(root)), title="Subsystems for this run")


def _run_option_cards(workflow: str, lane: str) -> list[tuple[str, str, DetailCard]]:
    """(value, label, card) rows for the run preflight main menu."""
    return [
        (
            "proceed",
            "Proceed — run now",
            DetailCard(
                current=f"workflow={workflow}, lane={lane}",
                effect="Starts the session and executes the run immediately.",
                recommended="Choose when the plan above matches your intent.",
                risk="The mutate node may edit files; gates and receipts record every step.",
                cli=f'opencontext run "<task>" --workflow {workflow} --lane {lane} --yes',
            ),
        ),
        (
            "workflow",
            "Change workflow (auto / oc-flow)",
            DetailCard(
                current=workflow,
                effect="Switches between explicit oc-flow and automatic workflow selection.",
                recommended="Use auto when unsure; it routes broad or high-risk tasks to SDD.",
                risk="auto may recommend SDD instead of executing OC Flow directly.",
                cli='opencontext run "<task>" --workflow <oc-flow|auto>',
            ),
        ),
        (
            "lane",
            "Change lane (fast / cheap / careful)",
            DetailCard(
                current=lane,
                effect="Adjusts context depth, diagnosis budget, and inspection strictness.",
                recommended="fast for everyday tasks; careful for risky edits; cheap saves tokens.",
                risk="cheap may gather too little context for complex tasks.",
                cli='opencontext run "<task>" --lane <fast|cheap|careful>',
            ),
        ),
        (
            "cancel",
            "Cancel",
            DetailCard(
                current="nothing has run yet",
                effect="Exits without starting a session or touching any file.",
                recommended="Choose when the task or the plan above needs rework.",
                risk="None — no state is created.",
                cli='opencontext simulate "<task>"  (preview without executing)',
            ),
        ),
    ]


def run_preflight(*, task: str, workflow: str, lane: str, profile: str, root: Path) -> RunDecision:
    """Interactive preflight loop for ``opencontext run``.

    Renders the briefing, then asks Proceed / Change workflow / Change lane /
    Cancel. Changes re-render the briefing with the updated plan.
    """
    while True:
        resolved_workflow, reason = _resolve_workflow(task, workflow)
        _render_run_briefing(task, workflow, resolved_workflow, reason, lane, profile, root)

        cards = _run_option_cards(workflow, lane)
        _render_option_cards("Options", [(label, card) for _, label, card in cards])
        choice = prompts.select(
            "Ready to run?",
            [(value, label) for value, label, _ in cards],
            default="proceed",
        )

        if choice == "workflow":
            workflow = str(
                prompts.select(
                    "Workflow",
                    [
                        ("oc-flow", "oc-flow — fast, local-first operational flow"),
                        ("auto", "auto — pick oc-flow or SDD from task class and risk"),
                    ],
                    default=workflow,
                )
            )
            continue
        if choice == "lane":
            lane = str(
                prompts.select(
                    "Lane",
                    [
                        ("fast", "fast — balanced depth and strictness (default)"),
                        ("cheap", "cheap — minimal context and diagnosis budget"),
                        ("careful", "careful — deepest context, strictest inspection"),
                    ],
                    default=lane,
                )
            )
            continue
        if choice == "cancel":
            return RunDecision(proceed=False, workflow=workflow, lane=lane)
        return RunDecision(proceed=True, workflow=workflow, lane=lane)


# ---------------------------------------------------------- oc-new preflight
@dataclass(frozen=True)
class OcNewDecision:
    """Outcome of the oc-new preflight: whether to start and the run's flow mode."""

    proceed: bool
    flow_mode: str


_FLOW_MODE_MEANINGS: dict[str, str] = {
    "automatic": "runs phases end-to-end without pausing (approval still gates apply)",
    "stepwise": "pauses for approval after every phase",
    "hybrid": "pauses at risky phases (spec, design, tasks, approval, verify, review)",
    "engram_only": "planning only; no code execution, artifacts to memory (no OpenSpec files)",
    "openspec_only": "planning only; writes OpenSpec artifacts, no code execution",
    "observe_only": "observation only; always pauses, never executes code or writes files",
}

_FLOW_MODE_STATIC_CARDS: dict[str, tuple[str, str]] = {
    # mode -> (recommended, risk)
    "automatic": (
        "Well-scoped changes where you trust the flow end-to-end.",
        "Least oversight between phases; the approval gate still protects apply.",
    ),
    "stepwise": (
        "High-stakes changes where every phase deserves review.",
        "Slowest mode — expect a confirmation after each phase.",
    ),
    "hybrid": (
        "The balanced default: autonomy on safe phases, review on risky ones.",
        "Early phases (explore, propose) run without a pause.",
    ),
    "engram_only": (
        "Capturing a plan into memory without touching the repository.",
        "No code is executed and no OpenSpec files are written.",
    ),
    "openspec_only": (
        "Producing a reviewable OpenSpec artifact trail without code changes.",
        "No code is executed; artifacts land under openspec/.",
    ),
    "observe_only": (
        "Dry-running the flow to see what it would do.",
        "Nothing is executed or written; every phase pauses.",
    ),
}


def _flow_mode_cards(active: str, source: str) -> list[tuple[str, str, DetailCard]]:
    """(value, label, card) rows for the execution-mode selector."""
    rows: list[tuple[str, str, DetailCard]] = []
    for mode, meaning in _FLOW_MODE_MEANINGS.items():
        recommended, risk = _FLOW_MODE_STATIC_CARDS[mode]
        current = f"active for this run (from {source})" if mode == active else "not selected"
        rows.append(
            (
                mode,
                f"{mode} — {meaning}",
                DetailCard(
                    current=current,
                    effect=f"For this run: {meaning}.",
                    recommended=recommended,
                    risk=risk,
                    cli=f"opencontext config set sdd.flow_mode {mode}",
                ),
            )
        )
    return rows


def _oc_new_briefing_lines(task: str, flow_mode: str, source: str, root: Path) -> list[str]:
    """Flow briefing: mode + meaning, phase list, and the project's SDD knobs."""
    try:
        from opencontext_core.oc_new.flow import OC_NEW_FLOW

        phases = " → ".join(phase.name for phase in OC_NEW_FLOW)
    except Exception:
        phases = (
            "explore → propose → spec → design → tasks → approval → apply "
            "→ verify → review → archive"
        )

    store_mode = "none"
    delivery = "plan-only"
    tdd_mode = "ask"
    track = "full"
    try:
        from opencontext_core.config import load_config_or_defaults
        from opencontext_core.config_resolver import resolve_config_path

        cfg = load_config_or_defaults(resolve_config_path(root), auto_detect=False)
        store_mode = str(cfg.sdd.artifact_store.mode.value)
        delivery = str(cfg.sdd.delivery_strategy.value)
        track = str(cfg.sdd.track)
        tdd_mode = str(cfg.harness.tdd_mode)
    except Exception:
        pass

    meaning = _FLOW_MODE_MEANINGS.get(flow_mode, flow_mode)
    return [
        f"Task              : {task}",
        f"Flow mode         : {flow_mode} (from {source}) — {meaning}",
        f"Phases            : {phases}",
        "Human gates       : approval always pauses before apply; the flow mode adds pauses on top",
        f"Artifact store    : {store_mode}",
        f"TDD mode          : {tdd_mode}",
        f"Delivery strategy : {delivery}",
        f"Track             : {track}",
    ]


def oc_new_preflight(*, task: str, flow_mode: str, source: str, root: Path) -> OcNewDecision:
    """Interactive preflight for ``opencontext oc-new start``.

    Explains the flow, asks for the execution mode (this run only — the
    persistence hint is printed, the config is never written), then confirms.
    """
    console.header("oc-new Preflight")
    briefing = "\n".join(_oc_new_briefing_lines(task, flow_mode, source, root))
    console.panel(briefing, title="Flow briefing")

    cards = _flow_mode_cards(flow_mode, source)
    _render_option_cards("Execution mode options", [(label, card) for _, label, card in cards])
    chosen = str(
        prompts.select(
            "Execution mode for this run",
            [(value, label) for value, label, _ in cards],
            default=flow_mode,
        )
    )
    console.dim(
        f"Applies to this run only. Persist with: opencontext config set sdd.flow_mode {chosen}"
    )

    if not prompts.confirm("Start the oc-new run now?", default=True):
        return OcNewDecision(proceed=False, flow_mode=chosen)
    return OcNewDecision(proceed=True, flow_mode=chosen)


# ------------------------------------------------------------- gate rendering
def render_gate_panel(state: Any) -> None:
    """Branded panel for a paused (request_approval) or blocked oc-new run.

    Names the gated phase, run progress, what happens next, and the exact
    commands to continue or inspect — replacing the raw next-action dump for
    the human path. The --json shape is rendered elsewhere and stays untouched.
    """
    action = state.next_action
    if action is None:
        return
    run_id = state.identity.run_id
    completed = [p.name for p in state.phases if p.status in {"passed", "warning", "skipped"}]
    total = len(state.phases)

    progress = f"{len(completed)}/{total} phases complete"
    if completed:
        progress += f" ({', '.join(completed)})"

    lines = [
        f"Kind        : {action.kind}",
        f"Phase       : {action.phase or '-'}",
        f"Progress    : {progress}",
        f"What's next : {action.instruction}",
    ]
    if action.expected_artifacts:
        lines.append(f"Expects     : {', '.join(action.expected_artifacts)}")
    if state.blocked_reason:
        lines.append(f"Resolve     : {state.blocked_reason}")

    lines.append("")
    if action.kind == "request_approval" and action.phase:
        lines.append(f"Continue : opencontext oc-new done {action.phase} --run-id {run_id}")
        lines.append("           (run the phase and place its expected artifacts first)")
    lines.append(f"Inspect  : opencontext oc-new status --run-id {run_id}")
    lines.append(f"Re-check : opencontext oc-new resume {run_id}")

    if action.kind == "request_approval":
        console.panel("\n".join(lines), title="Approval required", style="warning")
    else:
        console.panel("\n".join(lines), title="Run blocked", style="error")
