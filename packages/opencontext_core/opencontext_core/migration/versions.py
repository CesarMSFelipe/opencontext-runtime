"""Aggregate runtime/schema version block for ``opencontext version`` (REL-13).

Emits the book §8 block: the package version plus each independently-versioned
public schema line. Sourced from the canonical constants where they exist, with
the book's 1.0 compatibility set (§28) as the stable default otherwise.
"""

from __future__ import annotations

import importlib.metadata


def _package_version() -> str:
    for dist in ("opencontext-core", "opencontext-cli", "opencontext"):
        try:
            return importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "0.0.0"


def aggregate_versions() -> dict[str, str]:
    """Return the aggregate runtime + schema version block (book §8)."""
    return {
        "opencontext": _package_version(),
        "runtime_api": "v1",
        "workflow_schema": "v1",
        "plugin_api": "v1",
        "config_schema": "v2",
        "kg_schema": "v2",
        "memory_schema": "v1",
    }


__all__ = ["aggregate_versions"]
