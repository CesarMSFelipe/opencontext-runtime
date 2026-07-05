"""Real-evidence collector for the Runtime Health report (B9 / AVH-016).

The audit found ``opencontext health`` reporting ~0.46 with every dimension on a
fabricated neutral default — the caller passed no signals to
:meth:`RuntimeHealth.report`, so nothing was grounded in real project state.

This module closes that gap. :func:`collect_health_evidence` reads the evidence
that the runtime already persists under ``.opencontext/`` and projects it into the
keyword arguments :meth:`RuntimeHealth.report` already accepts (we wire, we do not
rebuild the scoring math):

* **cost calibration** — ``estimate_error_pct`` from recorded ``intelligence.cost
  .reported`` events (``telemetry/events.jsonl``);
* **benchmark trend** — whether the most recent benchmark run's *measured* results
  all succeeded (``telemetry/benchmark-history.json``);
* **selector accuracy** — the recorded ``next_node`` decisions across runs
  (``sessions/*/runs/*/decisions.json``), reusing
  :func:`decision_quality_metrics`.

A signal with no evidence on disk is simply OMITTED from the returned dict, so the
report marks that dimension ``UNMEASURED`` rather than inventing a score (build
rule #1: honesty). The collector never writes and never raises on a malformed
artifact — a broken file degrades to "no evidence".
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from opencontext_core.paths import StorageMode, resolve_workspace_path
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout


def collect_health_evidence(root: str | Path = ".") -> dict[str, Any]:
    """Collect real health-evidence kwargs for :meth:`RuntimeHealth.report`.

    Returns only the keys for which a genuine evidence source was found on disk;
    absent signals are left out so the report reports them ``UNMEASURED``.
    """
    root = Path(root)
    evidence: dict[str, Any] = {}

    cost_errs = _cost_error_pcts(root)
    if cost_errs:
        evidence["cost_error_pcts"] = cost_errs

    trend = _benchmark_trend(root)
    if trend is not None:
        evidence["efficiency_all_sufficient"] = trend

    decisions = _recorded_decisions(root)
    if decisions:
        evidence["decision_log"] = decisions

    return evidence


def _cost_error_pcts(root: Path) -> list[float]:
    """Estimate-error percentages from recorded cost-report events (book §6)."""
    out: list[float] = []
    for event in telemetry_layout.read_events(root):
        if event.get("event") != ri_events.COST_REPORTED:
            continue
        value = event.get("estimate_error_pct")
        if isinstance(value, (int, float)):
            out.append(float(value))
    return out


def _benchmark_trend(root: Path) -> bool | None:
    """Did the latest benchmark run's measured results all succeed? (book §12).

    ``None`` when no benchmark history exists (the gate stays UNMEASURED).
    """
    path = root / telemetry_layout.TELEMETRY_DIR / telemetry_layout.BENCHMARK_HISTORY_FILE
    if not path.exists():
        return None
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(history, list) or not history:
        return None
    latest = history[-1]
    results = latest.get("results", []) if isinstance(latest, dict) else []
    measured = [r for r in results if isinstance(r, dict) and r.get("measured")]
    if not measured:
        return None
    return all(bool(r.get("success")) for r in measured)


def _recorded_decisions(root: Path) -> list[SimpleNamespace]:
    """Recorded runtime decisions across runs, as objects with ``kind``/``governed_by``.

    Reused by :func:`decision_quality_metrics` to compute selector accuracy from
    the real ``next_node`` selections persisted by the OC Flow runner.
    """
    base = resolve_workspace_path(root, StorageMode.local) / "sessions"
    if not base.exists():
        return []
    out: list[SimpleNamespace] = []
    for decisions_json in base.glob("*/runs/*/decisions.json"):
        try:
            data = json.loads(decisions_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows = data.get("decisions", []) if isinstance(data, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(
                SimpleNamespace(
                    kind=str(row.get("kind", "")),
                    governed_by=row.get("governed_by"),
                )
            )
    return out


__all__ = ["collect_health_evidence"]
