"""REQ-06: Lease symbols are NOT in workflow.__all__ but still importable directly."""

from __future__ import annotations

import opencontext_core.workflow as wf


def test_lease_symbols_absent_from_all() -> None:
    """AgentCoordinationStore, AgentLease, AgentSignal must not be in __all__."""
    assert "AgentCoordinationStore" not in wf.__all__
    assert "AgentLease" not in wf.__all__
    assert "AgentLeaseStatus" not in wf.__all__
    assert "AgentSignal" not in wf.__all__
    assert "AgentSignalKind" not in wf.__all__


def test_lease_symbols_importable_from_module() -> None:
    """Direct module imports still work even after removal from __all__."""
    from opencontext_core.workflow.leases import (
        AgentCoordinationStore,
        AgentLease,
        AgentLeaseStatus,
    )
    from opencontext_core.workflow.signals import AgentSignal, AgentSignalKind

    # Just confirm the names are importable (no AttributeError / ImportError).
    assert AgentCoordinationStore is not None
    assert AgentLease is not None
    assert AgentLeaseStatus is not None
    assert AgentSignal is not None
    assert AgentSignalKind is not None


def test_star_import_excludes_lease_symbols() -> None:
    """from opencontext_core.workflow import * must not expose lease symbols."""
    import importlib
    import types

    tmp = types.ModuleType("_test_star_import")
    exec(
        "from opencontext_core.workflow import *",
        tmp.__dict__,
    )
    assert "AgentCoordinationStore" not in dir(tmp)
    assert "AgentLease" not in dir(tmp)
    assert "AgentSignal" not in dir(tmp)
    # Public workflow symbols should still be present.
    assert "WorkflowEngine" in dir(tmp)
