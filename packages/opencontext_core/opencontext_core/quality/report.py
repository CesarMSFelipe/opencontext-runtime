"""Quality report re-exports.

The historical :class:`QualityReport` lives in
:mod:`opencontext_core.quality.models`. This module re-exports it under the
``opencontext_core.quality.report`` import path so test code and external
callers that reference the public ``report`` submodule (mirroring the
``models.py`` / ``ci_checks.py`` / ``rules.py`` / ``baseline.py`` siblings)
do not fail with ``ModuleNotFoundError``.

Keep this module thin: the single source of truth for ``QualityReport``
remains :mod:`opencontext_core.quality.models`. Do not add new behaviour
here — only re-export from the canonical location.
"""

from __future__ import annotations

from opencontext_core.quality.models import (
    Finding,
    HealthScore,
    QualityMetrics,
    QualityReport,
    RuleVerdict,
)

__all__ = [
    "Finding",
    "HealthScore",
    "QualityMetrics",
    "QualityReport",
    "RuleVerdict",
]
