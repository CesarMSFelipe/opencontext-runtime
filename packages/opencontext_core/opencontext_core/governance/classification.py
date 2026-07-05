"""Data classification layer (REQ-data-gov-001, PR-R2-B).

Every ``KgNode`` / ``MemoryRecord`` / ``ContextItem`` / ``ProviderPayload`` carries a
``DataSensitivity`` tag inferred from source path + content type at ingest time.
Default is ``INTERNAL``; user-provided ``[data_governance] overrides`` in config.yaml
may force a specific level via glob patterns (e.g. ``"secrets/**": "RESTRICTED"``).

Layer: L3 (Governance). Read by L7 Provider Gateway (PR-012) before any outbound
call. Honors doc 34 (OC-DATAGOV-001).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from dataclasses import dataclass, field

from opencontext_core.compat import StrEnum
from opencontext_core.runtime.ids import new_kg_id

__all__ = [
    "ClassifiedNode",
    "DataSensitivity",
    "classify",
]


class DataSensitivity(StrEnum):
    """Four-level data sensitivity (OC-DATAGOV-001, doc 34)."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


@dataclass(frozen=True)
class ClassifiedNode:
    """A source artifact tagged with its data sensitivity."""

    node_id: str
    path: str
    content_type: str
    sensitivity: DataSensitivity
    rule: str | None = None  # the override glob that matched, if any
    extras: Mapping[str, str] = field(default_factory=dict)


def classify(
    path: str,
    content_type: str = "text/plain",
    overrides: Mapping[str, DataSensitivity] | None = None,
) -> ClassifiedNode:
    """Return a :class:`ClassifiedNode` for *path*.

    Resolution order:
        1. Walk ``overrides`` in insertion order; first glob match wins.
        2. Otherwise default to :attr:`DataSensitivity.INTERNAL`.
    """
    matched_rule: str | None = None
    matched_sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    if overrides:
        for pattern, sensitivity in overrides.items():
            if fnmatch.fnmatch(path, pattern):
                matched_rule = pattern
                matched_sensitivity = sensitivity
                break
    return ClassifiedNode(
        node_id=new_kg_id(f"{path}|{content_type}"),
        path=path,
        content_type=content_type,
        sensitivity=matched_sensitivity,
        rule=matched_rule,
    )
