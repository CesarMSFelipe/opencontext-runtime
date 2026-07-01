"""Data governance layer (PR-R2-B, doc 34).

Exposes classification, redaction, retention, and audit primitives. The module
is provider-neutral and has no hidden global state. See
``openspec/changes/opencontext-1-0-convergence/specs/data-governance-classification/spec.md``
for the full contract.
"""

from opencontext_core.governance.audit import AuditLog, AuditRecord
from opencontext_core.governance.classification import (
    ClassifiedNode,
    DataSensitivity,
    classify,
)
from opencontext_core.governance.redaction import (
    RedactionPipeline,
    RedactionResult,
    RedactionRule,
    apply_redaction,
)
from opencontext_core.governance.retention import (
    AuditHook,
    PurgeReceipt,
    RetentionPolicy,
    enforce_retention,
)

__all__ = [
    "AuditHook",
    "AuditLog",
    "AuditRecord",
    "ClassifiedNode",
    "DataSensitivity",
    "PurgeReceipt",
    "RedactionPipeline",
    "RedactionResult",
    "RedactionRule",
    "RetentionPolicy",
    "apply_redaction",
    "classify",
    "enforce_retention",
]
