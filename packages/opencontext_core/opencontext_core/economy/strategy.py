"""EconomyStrategy — decides token economy parameters per mode and phase.

NOTE: stdlib only — no external dependencies.

Economy modes:
  off       — full verbosity, no compression, large handoffs
  balanced  — compact handoffs with code snippets, moderate token cap
  aggressive — maximally compact handoffs, no code snippets, tight cap
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EconomyDecision:
    """Result of an economy strategy evaluation."""

    compact_handoff: bool
    include_code_snippets: bool
    max_handoff_tokens: int


# NOTE: Per-phase caps for aggressive mode — explore needs more context than archive.
_AGGRESSIVE_PHASE_CAPS: dict[str, int] = {
    "explore": 800,
    "propose": 600,
    "spec": 700,
    "design": 700,
    "tasks": 600,
    "approval": 400,
    "apply": 800,
    "verify": 600,
    "review": 600,
    "archive": 400,
}

_BALANCED_MAX = 1200
_OFF_MAX = 4000
_AGGRESSIVE_DEFAULT = 800


class EconomyStrategy:
    """Stateless strategy that maps (economy_mode, phase) to EconomyDecision."""

    @staticmethod
    def decide(mode: str, phase: str) -> EconomyDecision:
        """Return an EconomyDecision for *mode* and *phase*.

        Parameters
        ----------
        mode:
            One of "off", "balanced", "aggressive".
        phase:
            The conductor phase name (e.g. "explore", "apply").
        """
        if mode == "off":
            return EconomyDecision(
                compact_handoff=False,
                include_code_snippets=True,
                max_handoff_tokens=_OFF_MAX,
            )
        if mode == "aggressive":
            cap = _AGGRESSIVE_PHASE_CAPS.get(phase, _AGGRESSIVE_DEFAULT)
            return EconomyDecision(
                compact_handoff=True,
                include_code_snippets=False,
                max_handoff_tokens=cap,
            )
        # Default: "balanced"
        return EconomyDecision(
            compact_handoff=True,
            include_code_snippets=True,
            max_handoff_tokens=_BALANCED_MAX,
        )


def render_compact_handoff(handoff: Any) -> str:
    """Render *handoff* as a compact string starting with ``RUN ``.

    Accepts any object with attributes ``run_id``, ``phase``, ``task``,
    or a plain dict with those keys. Falls back gracefully for unknown shapes.
    """
    if isinstance(handoff, dict):
        run_id = handoff.get("run_id", "?")
        phase = handoff.get("phase", "?")
        task = str(handoff.get("task", ""))[:120]
    else:
        run_id = getattr(handoff, "run_id", "?")
        phase = getattr(handoff, "phase", "?")
        task = str(getattr(handoff, "task", ""))[:120]

    return f"RUN {run_id} | {phase} | {task}"


if __name__ == "__main__":
    # Self-check: verify spec scenarios.

    # balanced apply
    d = EconomyStrategy.decide("balanced", "apply")
    assert d.compact_handoff is True, f"Expected compact_handoff=True, got {d}"
    assert d.include_code_snippets is True, f"Expected include_code_snippets=True, got {d}"

    # aggressive explore
    d2 = EconomyStrategy.decide("aggressive", "explore")
    assert d2.max_handoff_tokens <= 800, f"Expected <= 800, got {d2.max_handoff_tokens}"
    assert d2.include_code_snippets is False, f"Expected include_code_snippets=False, got {d2}"

    # off
    d3 = EconomyStrategy.decide("off", "apply")
    assert d3.compact_handoff is False

    # render_compact_handoff starts with "RUN "
    rendered = render_compact_handoff({"run_id": "ocnew-abc", "phase": "explore", "task": "test"})
    assert rendered.startswith("RUN "), f"Expected 'RUN ' prefix, got: {rendered!r}"

    print("economy/strategy.py self-check passed.")
