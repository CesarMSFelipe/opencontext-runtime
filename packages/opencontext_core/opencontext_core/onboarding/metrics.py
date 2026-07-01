"""Developer-experience metrics for the first-run journey (PR-R2-D).

Spec: ``openspec/changes/opencontext-1-0-convergence/specs/developer-experience-onboarding/spec.md``

The wizard (``OnboardingWizard``) emits one ``DxMetrics`` at the end of the
journey. The success-metrics dashboard (PR-R2-G) consumes the same shape so
the two PRs share a single canonical record instead of two ad-hoc dataclasses.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DxMetrics:
    """Structured record of a single first-run onboarding.

    Fields:
        time_to_first_context_seconds: Wall-clock seconds from wizard start
            to ``run_onboarding`` returning successfully. The spec's headline
            KPI for REQ-dx-onb-001.
        setup_success_rate: 0.0..1.0 ratio of setups that finished cleanly.
            ``1.0`` for a single-shot run; aggregated to a ratio in the
            dashboard (PR-R2-G).
        first_run_completed: True once all four wizard steps reached ``ok``.
        indexed_files / indexed_symbols / knowledge_graph_{nodes,edges}:
            carried from the ``OnboardingResult`` so callers can correlate
            performance with project size.
        active_clients: tuple of agent clients the wizard configured. Tuples
            keep the record hashable (frozen dataclass). Lists are accepted
            at the constructor and normalised to tuples.
    """

    time_to_first_context_seconds: float = 0.0
    setup_success_rate: float = 0.0
    first_run_completed: bool = False
    indexed_files: int = 0
    indexed_symbols: int = 0
    knowledge_graph_nodes: int = 0
    knowledge_graph_edges: int = 0
    active_clients: tuple[str, ...] = ()

    def __init__(
        self,
        time_to_first_context_seconds: float = 0.0,
        setup_success_rate: float = 0.0,
        first_run_completed: bool = False,
        indexed_files: int = 0,
        indexed_symbols: int = 0,
        knowledge_graph_nodes: int = 0,
        knowledge_graph_edges: int = 0,
        active_clients: Iterable[str] | tuple[str, ...] = (),
    ) -> None:
        if time_to_first_context_seconds < 0:
            raise ValueError(
                f"time_to_first_context_seconds must be >= 0, got {time_to_first_context_seconds}"
            )
        if not 0.0 <= setup_success_rate <= 1.0:
            raise ValueError(f"setup_success_rate must be in [0, 1], got {setup_success_rate}")
        # Coerce lists / tuples / None into a tuple (frozen dataclass +
        # hashable record). ``tuple(...)`` raises on generators, which is
        # the desired behaviour for the field type.
        clients = () if active_clients is None else tuple(active_clients)
        # Bypass the frozen guard — __init__ is the single source of truth.
        object.__setattr__(
            self, "time_to_first_context_seconds", float(time_to_first_context_seconds)
        )
        object.__setattr__(self, "setup_success_rate", float(setup_success_rate))
        object.__setattr__(self, "first_run_completed", bool(first_run_completed))
        object.__setattr__(self, "indexed_files", int(indexed_files))
        object.__setattr__(self, "indexed_symbols", int(indexed_symbols))
        object.__setattr__(self, "knowledge_graph_nodes", int(knowledge_graph_nodes))
        object.__setattr__(self, "knowledge_graph_edges", int(knowledge_graph_edges))
        object.__setattr__(self, "active_clients", clients)

    @classmethod
    def from_result(
        cls,
        result: Any,
        *,
        time_to_first_context_seconds: float = 0.0,
        first_run_completed: bool = True,
    ) -> DxMetrics:
        """Build a ``DxMetrics`` from an ``OnboardingResult`` + timing.

        Centralises the projection so the wizard and the CLI emit identical
        records.
        """
        clients: Iterable[str] = getattr(result, "active_clients", ()) or ()
        return cls(
            time_to_first_context_seconds=float(time_to_first_context_seconds),
            setup_success_rate=1.0 if first_run_completed else 0.0,
            first_run_completed=first_run_completed,
            indexed_files=int(getattr(result, "indexed_files", 0) or 0),
            indexed_symbols=int(getattr(result, "indexed_symbols", 0) or 0),
            knowledge_graph_nodes=int(getattr(result, "knowledge_graph_nodes", 0) or 0),
            knowledge_graph_edges=int(getattr(result, "knowledge_graph_edges", 0) or 0),
            active_clients=tuple(clients),
        )


__all__ = ["DxMetrics"]
