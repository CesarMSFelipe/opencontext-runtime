"""OpenContext Studio — read-only data layer over run evidence (PR-014).

This package is the **only** boundary Studio uses to touch runtime data, and it
is observe-only: :class:`~opencontext_core.studio.reader.StudioReader` exposes no
write/mutate method (SPEC-STU-014-11). Importing this package pulls in only the
framework-free data layer (view models + reader + redaction); the optional web
shell (``app``/``server``, which import FastAPI/uvicorn) is imported lazily by
the CLI ``studio`` command so the runtime stays headless without Studio
(SPEC-STU-014-12).
"""

from __future__ import annotations

from opencontext_core.studio.reader import StudioReader
from opencontext_core.studio.redaction import redact_value
from opencontext_core.studio.views import (
    StudioBrainView,
    StudioCacheView,
    StudioCapabilityView,
    StudioConfigView,
    StudioContextView,
    StudioCostView,
    StudioDecisionLogView,
    StudioHarnessView,
    StudioKgView,
    StudioLearningView,
    StudioMemoryView,
    StudioReceiptView,
    StudioSession,
    StudioTimeline,
    StudioTimelines,
)

__all__ = [
    "StudioBrainView",
    "StudioCacheView",
    "StudioCapabilityView",
    "StudioConfigView",
    "StudioContextView",
    "StudioCostView",
    "StudioDecisionLogView",
    "StudioHarnessView",
    "StudioKgView",
    "StudioLearningView",
    "StudioMemoryView",
    "StudioReader",
    "StudioReceiptView",
    "StudioSession",
    "StudioTimeline",
    "StudioTimelines",
    "redact_value",
]
