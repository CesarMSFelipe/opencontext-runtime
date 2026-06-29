"""Runtime execution modes (SPEC RC-011).

The six modes from ``02-runtime-architecture.md`` §25. ``dry_run`` must not
perform mutations; the runner honours this in the node pipeline.
"""

from __future__ import annotations

from opencontext_core.compat import StrEnum


class RuntimeMode(StrEnum):
    """Supported runtime execution modes (book §25, 6 modes)."""

    run_to_completion = "run_to_completion"
    interactive = "interactive"
    step = "step"
    dry_run = "dry_run"
    simulate = "simulate"
    resume = "resume"
