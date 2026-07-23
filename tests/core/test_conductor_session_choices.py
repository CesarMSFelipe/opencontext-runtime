"""S1 slice: the session's guided choices ride the agent-facing handoff.

The oc-new conductor hands work off to the agent by emitting a ``spawn_subagent``
NextAction carrying a ``metadata`` block and an ``instruction`` string the agent
reads. This slice threads the session's this-run-only guided SDD choices
(flow_mode + artifact store / delivery / chain) into that handoff so a later
phase/skill can READ and HONOUR them.

Failing tests (TDD):
- start() with explicit SessionChoices → the first spawn_subagent handoff's
  metadata['session_choices'] carries exactly those values, and they also appear
  in the instruction text the agent consumes.
- start() WITHOUT session choices → the handoff defaults every choice from the
  project's resolved SDD config (opencontext.yaml).
- flow_mode always rides the handoff (from the run config).
- Passing session_choices to the conductor does NOT write the config file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.models import SessionChoices


def _first_handoff_metadata(state: object) -> dict:
    """The metadata block of the first spawn_subagent handoff emitted for a run."""
    na = getattr(state, "next_action", None)
    assert na is not None, "expected a next_action"
    assert na.kind == "spawn_subagent", f"expected spawn_subagent, got {na.kind!r}"
    return na.metadata


def test_explicit_session_choices_ride_the_handoff(tmp_path: Path) -> None:
    """Explicit choices appear in the handoff metadata and the instruction text."""
    conductor = OcNewConductor(root=tmp_path)
    choices = SessionChoices(
        artifact_store="engram",
        delivery_strategy="auto-chain",
        chain_strategy="stacked-to-main",
    )

    state = conductor.start("add health command", session_choices=choices)

    meta = _first_handoff_metadata(state)
    block = meta["session_choices"]
    assert block["artifact_store"] == "engram"
    assert block["delivery_strategy"] == "auto-chain"
    assert block["chain_strategy"] == "stacked-to-main"
    # flow_mode always rides the handoff (default automatic here — no config).
    assert block["flow_mode"] == "automatic"

    # The agent reads the instruction text too — the choices must be labelled there.
    instruction = state.next_action.instruction
    assert "artifact_store=engram" in instruction
    assert "delivery=auto-chain" in instruction
    assert "chain=stacked-to-main" in instruction
    assert "flow_mode=automatic" in instruction


def test_handoff_defaults_choices_from_config_when_not_provided(tmp_path: Path) -> None:
    """No session choices → the handoff seeds each choice from the SDD config."""
    (tmp_path / "opencontext.yaml").write_text(
        yaml.dump(
            {
                "sdd": {
                    "flow_mode": "automatic",
                    "artifact_store": {"mode": "hybrid"},
                    "delivery_strategy": "ask-on-risk",
                    "chain_strategy": "feature-branch-chain",
                }
            }
        ),
        encoding="utf-8",
    )
    conductor = OcNewConductor(root=tmp_path)

    state = conductor.start("add health command")

    block = _first_handoff_metadata(state)["session_choices"]
    assert block["artifact_store"] == "hybrid"
    assert block["delivery_strategy"] == "ask-on-risk"
    assert block["chain_strategy"] == "feature-branch-chain"
    assert block["flow_mode"] == "automatic"


def test_partial_choices_fall_back_per_field_to_config(tmp_path: Path) -> None:
    """A field left empty defaults from config; a chosen field overrides it."""
    (tmp_path / "opencontext.yaml").write_text(
        yaml.dump(
            {
                "sdd": {
                    "artifact_store": {"mode": "openspec"},
                    "delivery_strategy": "single-pr",
                    "chain_strategy": "feature-branch-chain",
                }
            }
        ),
        encoding="utf-8",
    )
    conductor = OcNewConductor(root=tmp_path)
    # Only artifact_store chosen this run; the rest fall back to config.
    choices = SessionChoices(artifact_store="engram")

    state = conductor.start("add health command", session_choices=choices)

    block = _first_handoff_metadata(state)["session_choices"]
    assert block["artifact_store"] == "engram"  # this-run override
    assert block["delivery_strategy"] == "single-pr"  # from config
    assert block["chain_strategy"] == "feature-branch-chain"  # from config


def test_session_choices_do_not_write_config_file(tmp_path: Path) -> None:
    """Passing session choices to the conductor never writes opencontext.yaml."""
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(
        "sdd:\n  flow_mode: automatic\n  delivery_strategy: plan-only\n",
        encoding="utf-8",
    )
    before = config_path.read_text(encoding="utf-8")
    conductor = OcNewConductor(root=tmp_path)

    conductor.start(
        "add health command",
        session_choices=SessionChoices(
            artifact_store="engram",
            delivery_strategy="auto-chain",
            chain_strategy="stacked-to-main",
        ),
    )

    assert config_path.read_text(encoding="utf-8") == before


def test_session_choices_persist_on_run_state_for_resume(tmp_path: Path) -> None:
    """The choices are saved on the run state so resume() forwards the same handoff."""
    conductor = OcNewConductor(root=tmp_path)
    choices = SessionChoices(
        artifact_store="engram",
        delivery_strategy="auto-chain",
        chain_strategy="stacked-to-main",
    )

    started = conductor.start("add health command", session_choices=choices)
    resumed = conductor.resume(started.identity.run_id)

    assert resumed.session_choices is not None
    assert resumed.session_choices.artifact_store == "engram"
    block = _first_handoff_metadata(resumed)["session_choices"]
    assert block["artifact_store"] == "engram"
    assert block["delivery_strategy"] == "auto-chain"
