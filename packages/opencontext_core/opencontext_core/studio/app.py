"""OpenContext Studio web shell — deprecation shim (PR-014).

This module previously provided an independent FastAPI app with session-oriented
``/api/*`` routes and SinkGuard redaction. The real Studio API now lives in
:mod:`opencontext_studio.server_v2` (``/api/v2/*`` routes with StudioReader
wiring and the same SinkGuard redaction); this module is a thin re-export shim
so callers that still reference ``opencontext_core.studio.app.create_app`` keep
working while the migration completes.

.. deprecated::
    Import :func:`opencontext_studio.server_v2.create_v2_app` directly.
    This shim will be removed in a future milestone.

NOTE: FastAPI is imported lazily (inside ``create_app``) so that
``opencontext_core.studio.app`` is not loaded at ``opencontext_core.studio``
package-import time (SPEC-STU-014-12).
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any


def create_app(root: Path | str = ".") -> Any:
    """Return the v2 Studio FastAPI app bound to *root*.

    .. deprecated::
        Call :func:`opencontext_studio.server_v2.create_v2_app` directly.
        This wrapper emits a :exc:`DeprecationWarning` on every call.
    """
    warnings.warn(
        "opencontext_core.studio.app.create_app is deprecated; "
        "use opencontext_studio.server_v2.create_v2_app directly.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Lazy: core has no install-time dependency on the studio package; the
    # shim only works where opencontext_studio is installed.
    from opencontext_studio.server_v2 import create_v2_app

    return create_v2_app(root=root)
