"""SDD Orchestrator for managing the full SDD lifecycle.

Coordinates the 7 phases of Spec-Driven Development:
propose -> spec -> design -> tasks -> apply -> verify -> archive
"""

from __future__ import annotations

from opencontext_core.agents.artifact_store import (
    ArtifactStore,
    EngramStore,
    HybridStore,
    NoneStore,
    OpenSpecStore,
)
from opencontext_core.agents.dag_state import DAGState
from opencontext_core.agents.result_contract import PhaseResult
from opencontext_core.agents.sdd_guardrails import (
    evaluate_guardrails,
    get_guardrails_for_phase,
)
from opencontext_core.config import (
    ArtifactStoreMode,
    SDDConfig,
)

PHASE_ORDER = [
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "review",
    "archive",
]

# Phase dependencies: which phases must complete before this one
PHASE_DEPENDENCIES: dict[str, list[str]] = {
    "explore": [],
    "propose": ["explore"],
    "spec": ["propose"],
    "design": ["propose"],
    "tasks": ["spec", "design"],
    "apply": ["tasks"],
    "verify": ["apply"],
    "review": ["verify"],
    "archive": ["review"],
}

# Workflow tracks: each track defines its own phase order and dependencies
WORKFLOW_TRACKS: dict[str, dict[str, object]] = {
    "quick": {
        "phases": ["explore", "apply", "verify"],
        "deps": {
            "explore": [],
            "apply": ["explore"],
            "verify": ["apply"],
        },
    },
    "standard": {
        "phases": ["explore", "spec", "design", "apply", "verify"],
        "deps": {
            "explore": [],
            "spec": ["explore"],
            "design": ["explore"],
            "apply": ["spec", "design"],
            "verify": ["apply"],
        },
    },
    "full": {
        "phases": PHASE_ORDER,
        "deps": PHASE_DEPENDENCIES,
    },
    "sdd": {
        "phases": PHASE_ORDER,
        "deps": PHASE_DEPENDENCIES,
    },
    "full+judgment": {
        "phases": [*PHASE_ORDER, "judgment"],
        "deps": {**PHASE_DEPENDENCIES, "judgment": ["verify"]},
    },
    "full+gga": {
        "phases": [*PHASE_ORDER, "gga"],
        "deps": {**PHASE_DEPENDENCIES, "gga": ["verify"]},
    },
    "full+quality": {
        "phases": [*PHASE_ORDER, "gga", "judgment"],
        "deps": {**PHASE_DEPENDENCIES, "gga": ["verify"], "judgment": ["gga"]},
    },
}


class SDDOrchestrator:
    """Orchestrates the full SDD lifecycle."""

    def __init__(self, config: SDDConfig | None = None) -> None:
        self.config = config or SDDConfig()
        self.store = self._create_store()
        self.state: DAGState | None = None
        self._track = getattr(self.config, "track", "full")

    def _get_track_phases(self) -> list[str]:
        """Get phase list for the active track."""

        track_data = WORKFLOW_TRACKS.get(self._track, WORKFLOW_TRACKS["full"])
        phases = track_data["phases"]
        assert isinstance(phases, list)
        return phases

    def _get_track_deps(self) -> dict[str, list[str]]:
        """Get dependency map for the active track."""

        track_data = WORKFLOW_TRACKS.get(self._track, WORKFLOW_TRACKS["full"])
        deps = track_data["deps"]
        assert isinstance(deps, dict)
        result: dict[str, list[str]] = {}
        for k, v in deps.items():
            assert isinstance(v, list)
            result[k] = v
        return result

    def _create_store(self) -> ArtifactStore:
        """Create artifact store based on config."""

        mode = self.config.artifact_store.mode

        if mode == ArtifactStoreMode.ENGRAM:
            return EngramStore()
        elif mode == ArtifactStoreMode.OPEN_SPEC:
            return OpenSpecStore(root=self.config.artifact_store.openspec.path)
        elif mode == ArtifactStoreMode.HYBRID:
            return HybridStore(openspec_root=self.config.artifact_store.openspec.path)
        else:
            return NoneStore()

    def start_change(self, change_name: str) -> DAGState:
        """Initialize a new SDD change."""

        self.state = DAGState(change=change_name)
        return self.state

    def can_run_phase(self, phase: str) -> bool:
        """Check if a phase can run (track-valid and all dependencies completed).

        Returns False if the phase is not part of the active track.
        """

        if self.state is None:
            return False

        track_phases = self._get_track_phases()
        if phase not in track_phases:
            return False

        deps = self._get_track_deps().get(phase, [])
        return all(self.state.is_phase_completed(dep) for dep in deps)

    def get_next_phases(self) -> list[str]:
        """Get list of phases that are ready to run in the active track."""

        if self.state is None:
            return []

        track_phases = self._get_track_phases()
        ready: list[str] = []
        for phase in track_phases:
            if not self.state.is_phase_completed(phase) and self.can_run_phase(phase):
                ready.append(phase)

        return ready

    def run_phase(self, phase: str, content: str) -> PhaseResult:
        """Run a single SDD phase.

        Runs guardrail evaluation on phase content, then persists artifact.

        Args:
            phase: Phase name.
            content: Phase artifact content.

        Returns:
            Phase result.
        """

        if self.state is None:
            return PhaseResult(
                status="blocked",
                executive_summary="No active change. Call start_change() first.",
            )

        if not self.can_run_phase(phase):
            track_phases = self._get_track_phases()
            if phase not in track_phases:
                return PhaseResult(
                    status="blocked",
                    executive_summary=(
                        f"Phase '{phase}' is not in the active track '{self._track}'. "
                        f"Track phases: {track_phases}"
                    ),
                )
            deps = self._get_track_deps().get(phase, [])
            missing = [d for d in deps if not self.state.is_phase_completed(d)]
            return PhaseResult(
                status="blocked",
                executive_summary=f"Dependencies not met: {missing}",
            )

        # Evaluate guardrails
        hits = evaluate_guardrails(phase, content)
        warnings: list[str] = []
        for hit in hits:
            if hit.severity == "block":
                return PhaseResult(
                    status="blocked",
                    executive_summary=f"Guardrail block: {hit.name}",
                    detailed_report=hit.counter_argument,
                    warnings=warnings,
                )
            warnings.append(f"[{hit.name}] {hit.counter_argument}")

        # Save artifact
        artifact_ref = self.store.save(self.state.change, phase, content)

        self.state.mark_completed(phase)
        self.state.mark_artifact_saved(phase)

        return PhaseResult(
            status="success",
            executive_summary=f"Phase '{phase}' completed for '{self.state.change}'.",
            artifacts=[artifact_ref],
            warnings=warnings,
            next_recommended=self._get_next_recommended(),
        )

    def _agent_contract_md(self, phase: str) -> str:
        """Generate the agent contract markdown for a phase, including guardrails.

        Args:
            phase: Phase name.

        Returns:
            Markdown string with agent instructions and guardrails.
        """

        md = f"# Agent Contract: {phase}\n\n"
        md += f"You are executing the **{phase}** phase of the SDD lifecycle.\n"
        md += "Follow the spec and design documents for this change.\n"

        guardrails = get_guardrails_for_phase(phase)
        if guardrails:
            md += "\n## Guardrails\n\n"
            md += "Watch for these common anti-patterns:\n\n"
            for entry in guardrails:
                md += f"- **{entry.name}**: {entry.rationalization}\n"
                md += f"  - *Counter-argument*: {entry.counter_argument}\n"
            md += "\n"

        return md

    def _get_next_recommended(self) -> str:
        """Determine the next recommended phase."""

        ready = self.get_next_phases()
        if ready:
            return ready[0]

        if self.state and self.state.phase == "archive":
            return "none"

        return "none"

    def get_state(self) -> DAGState | None:
        """Get current DAG state."""

        return self.state

    def recover_state(self, content: str) -> bool:
        """Recover state from persisted content.

        Args:
            content: Persisted state string.

        Returns:
            True if recovery succeeded.
        """

        state = DAGState.recover(content)
        if state is not None:
            self.state = state
            return True
        return False

    def get_artifact(self, phase: str) -> str | None:
        """Load an artifact for the current change."""

        if self.state is None:
            return None

        return self.store.load(self.state.change, phase)

    def is_complete(self) -> bool:
        """Check if all phases in the active track are completed."""

        if self.state is None:
            return False

        return all(self.state.is_phase_completed(phase) for phase in self._get_track_phases())
