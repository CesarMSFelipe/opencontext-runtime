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
    "archive": ["verify"],
}


class SDDOrchestrator:
    """Orchestrates the full SDD lifecycle."""

    def __init__(self, config: SDDConfig | None = None) -> None:
        self.config = config or SDDConfig()
        self.store = self._create_store()
        self.state: DAGState | None = None

    def _create_store(self) -> ArtifactStore:
        """Create artifact store based on config."""

        mode = self.config.artifact_store.mode

        if mode == ArtifactStoreMode.ENGRAM:
            return EngramStore()
        elif mode == ArtifactStoreMode.OPEN_SPEC:
            return OpenSpecStore(
                root=self.config.artifact_store.openspec.path
            )
        elif mode == ArtifactStoreMode.HYBRID:
            return HybridStore(
                openspec_root=self.config.artifact_store.openspec.path
            )
        else:
            return NoneStore()

    def start_change(self, change_name: str) -> DAGState:
        """Initialize a new SDD change."""

        self.state = DAGState(change=change_name)
        return self.state

    def can_run_phase(self, phase: str) -> bool:
        """Check if a phase can run (all dependencies completed)."""

        if self.state is None:
            return False

        deps = PHASE_DEPENDENCIES.get(phase, [])
        return all(self.state.is_phase_completed(dep) for dep in deps)

    def get_next_phases(self) -> list[str]:
        """Get list of phases that are ready to run."""

        if self.state is None:
            return []

        ready: list[str] = []
        for phase in PHASE_ORDER:
            if (
                not self.state.is_phase_completed(phase)
                and self.can_run_phase(phase)
            ):
                ready.append(phase)

        return ready

    def run_phase(self, phase: str, content: str) -> PhaseResult:
        """Run a single SDD phase.

        In a real implementation, this would delegate to a sub-agent.
        For now, it creates the artifact and updates state.

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
            deps = PHASE_DEPENDENCIES.get(phase, [])
            missing = [d for d in deps if not self.state.is_phase_completed(d)]
            return PhaseResult(
                status="blocked",
                executive_summary=f"Dependencies not met: {missing}",
            )

        # Save artifact
        artifact_ref = self.store.save(
            self.state.change, phase, content
        )

        # Update state
        self.state.mark_completed(phase)
        self.state.mark_artifact_saved(phase)

        return PhaseResult(
            status="success",
            executive_summary=f"Phase '{phase}' completed for '{self.state.change}'.",
            artifacts=[artifact_ref],
            next_recommended=self._get_next_recommended(),
        )

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
        """Check if all phases are completed."""

        if self.state is None:
            return False

        return all(
            self.state.is_phase_completed(phase)
            for phase in PHASE_ORDER
        )
