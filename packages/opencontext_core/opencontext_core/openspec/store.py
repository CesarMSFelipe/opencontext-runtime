"""OpenSpec store re-export.

NOTE: OpenSpecPaths does NOT exist in artifact_store.py — do not re-export it.
This module exposes only OpenSpecStore at the opencontext_core.openspec.store path.
"""

from opencontext_core.agents.artifact_store import OpenSpecStore as OpenSpecStore

__all__ = ["OpenSpecStore"]
