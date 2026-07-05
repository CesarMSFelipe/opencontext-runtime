"""F4: OcNewConductor reads sdd.flow_mode from opencontext.yaml when no explicit config given.

When `start()` is called with `config=None` (i.e., the user did not pass --flow),
the conductor must default the flow_mode from the project's opencontext.yaml
`sdd.flow_mode` field rather than blindly defaulting to 'automatic'.

Failing tests:
- yaml sets sdd.flow_mode=stepwise + config=None → conductor start returns state with stepwise mode.
- yaml absent → conductor falls back to 'automatic' (the AgenticFlowConfig default).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.oc_new.conductor import OcNewConductor


def _write_yaml_with_flow_mode(root: Path, flow_mode: str) -> None:
    """Write a minimal opencontext.yaml that sets sdd.flow_mode."""
    data = {"sdd": {"flow_mode": flow_mode}}
    (root / "opencontext.yaml").write_text(yaml.dump(data), encoding="utf-8")


def test_yaml_flow_mode_stepwise_is_used_when_no_explicit_config(tmp_path: Path) -> None:
    """yaml sdd.flow_mode=stepwise + config=None → conductor adopts stepwise."""
    _write_yaml_with_flow_mode(tmp_path, "stepwise")
    conductor = OcNewConductor(root=tmp_path)

    state = conductor.start("test task", config=None)

    assert state.config is not None, "Expected conductor to build a config from yaml"
    from opencontext_core.agentic.config import FlowMode

    assert state.config.flow_mode == FlowMode.STEPWISE, (
        f"Expected flow_mode=stepwise from yaml, got {state.config.flow_mode!r}"
    )


def test_yaml_absent_defaults_to_automatic(tmp_path: Path) -> None:
    """No opencontext.yaml → conductor defaults to automatic flow_mode."""
    # tmp_path has no opencontext.yaml
    conductor = OcNewConductor(root=tmp_path)

    state = conductor.start("test task", config=None)

    from opencontext_core.agentic.config import FlowMode

    if state.config is not None:
        assert state.config.flow_mode == FlowMode.AUTOMATIC, (
            f"Expected automatic flow_mode without yaml, got {state.config.flow_mode!r}"
        )


def test_explicit_config_wins_over_yaml(tmp_path: Path) -> None:
    """When an explicit config is passed, yaml sdd.flow_mode must be ignored."""
    _write_yaml_with_flow_mode(tmp_path, "stepwise")

    from opencontext_core.agentic.config import AgenticFlowConfig, FlowMode

    explicit_config = AgenticFlowConfig(flow_mode=FlowMode.AUTOMATIC)
    conductor = OcNewConductor(root=tmp_path)

    state = conductor.start("test task", config=explicit_config)

    assert state.config is not None
    assert state.config.flow_mode == FlowMode.AUTOMATIC, (
        f"Explicit config must not be overridden by yaml. Got {state.config.flow_mode!r}"
    )
