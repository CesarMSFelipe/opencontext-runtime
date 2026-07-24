"""Guided preflight for `opencontext oc-new start` — flow briefing before start.

Failing tests (TDD):
- On an interactive TTY, starting a run first renders a branded briefing: the
  resolved flow_mode + what it means, the phase list, artifact store mode, TDD
  mode, and delivery strategy — then asks for the execution mode and confirms.
- After the execution mode, three more guided detail-card selectors ask
  predefined choices for THIS RUN ONLY: artifact store, delivery strategy, and
  (only when delivery is not plan-only/single-pr) chain strategy. Each defaults
  to the resolved SDDConfig value and the config file is never written.
- The chosen flow mode applies to THIS RUN ONLY (opencontext.yaml untouched) and
  a persistence hint (`opencontext config set sdd.flow_mode <mode>`) is printed.
- --json, --yes, --non-interactive, and non-TTY skip the preflight entirely.
- Declining the confirmation starts nothing.
- --json output shape is unchanged (pure JSON state dump).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from opencontext_cli.commands.oc_new_cmd import handle_oc_new


def _args(
    tmp_path: Path,
    *,
    task: str = "add health check",
    flow: str | None = None,
    json_out: bool = False,
    yes: bool = False,
    non_interactive: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        root=str(tmp_path),
        json_out=json_out,
        oc_new_command="start",
        task=task,
        flow=flow,
        yes=yes,
        non_interactive=non_interactive,
    )


def _tty(value: bool) -> Any:
    return patch("opencontext_cli.flow_preflight._is_tty", return_value=value)


def _default_dispatch() -> Any:
    """side_effect returning each selector's own ``default`` (keeps values valid).

    The preflight now runs four selectors (flow mode, artifact store, delivery
    strategy, chain strategy). A single ``return_value`` would feed one string to
    all of them; dispatching to each selector's ``default`` keeps every choice a
    legal enum value while still exercising every prompt.
    """

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        return kw.get("default")

    return _select


def test_preflight_shown_on_tty_and_confirm_starts(tmp_path: Path, capsys: Any) -> None:
    """TTY start renders the flow briefing, asks, and starts on confirmation."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_default_dispatch()) as sel,
        patch("opencontext_core.prompts.confirm", return_value=True) as conf,
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    assert sel.called and conf.called
    # Briefing content: mode meanings, phases, store/TDD/delivery knobs.
    assert "automatic" in out
    assert "stepwise" in out
    assert "hybrid" in out
    assert "explore" in out and "apply" in out and "archive" in out
    assert "artifact store" in out.lower()
    assert "tdd" in out.lower()
    assert "delivery" in out.lower()
    # Detail-card format per option (config-TUI style).
    assert "Current:" in out
    assert "Effect:" in out
    assert "Recommended:" in out
    assert "Risk / note:" in out
    assert "CLI:" in out
    # The run actually started.
    assert "spawn_subagent" in out


def test_preflight_asks_the_three_guided_selectors_on_tty(tmp_path: Path, capsys: Any) -> None:
    """After execution mode, artifact-store / delivery / chain selectors are shown.

    Each selector must offer the canonical predefined options and seed its
    ``default`` from the project's SDDConfig defaults (none / plan-only /
    stacked-to-main here).
    """
    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_default_dispatch()) as sel,
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    # Collect (option-values, default) per select call for assertions.
    calls = []
    for call in sel.call_args_list:
        choices = call.args[1] if len(call.args) > 1 else call.kwargs["choices"]
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        calls.append((values, call.kwargs.get("default")))

    # Flow mode + artifact store + delivery == three selectors. The chain
    # selector is skipped here because the config-default delivery is plan-only
    # (its dedicated coverage is test_preflight_chain_selector_shown_when_delivery_chains).
    assert len(calls) == 3

    # Artifact-store selector: canonical options, default from config (none).
    store_call = next(
        c for c in calls if "hybrid" in c[0] and "openspec" in c[0] and "none" in c[0]
    )
    assert set(store_call[0]) >= {"hybrid", "openspec", "engram", "none"}
    assert store_call[1] == "none"

    # Delivery-strategy selector: canonical options, default from config (plan-only).
    delivery_call = next(c for c in calls if "ask-on-risk" in c[0] and "single-pr" in c[0])
    assert set(delivery_call[0]) >= {
        "ask-on-risk",
        "single-pr",
        "auto-chain",
        "exception-ok",
        "plan-only",
    }
    assert delivery_call[1] == "plan-only"


def test_preflight_selectors_have_detail_card_lines(tmp_path: Path, capsys: Any) -> None:
    """Each guided selector renders its choices as config-TUI detail cards."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_default_dispatch()),
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    # Detail-card five-line contract + the option titles.
    assert "Current:" in out
    assert "Effect:" in out
    assert "Recommended:" in out
    assert "Risk / note:" in out
    assert "CLI:" in out
    assert "artifact store" in out.lower()
    assert "delivery" in out.lower()
    # This-run-only persistence hints for the new choices.
    assert "opencontext config set sdd.artifact_store.mode" in out
    assert "opencontext config set sdd.delivery_strategy" in out


def test_preflight_choices_apply_this_run_only_config_untouched(
    tmp_path: Path, capsys: Any
) -> None:
    """Non-default choices apply to this run; opencontext.yaml is never written."""
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(
        "sdd:\n  flow_mode: automatic\n  delivery_strategy: plan-only\n",
        encoding="utf-8",
    )
    before = config_path.read_text(encoding="utf-8")

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "hybrid" in values and "engram" in values:  # artifact-store selector
            return "hybrid"
        if "ask-on-risk" in values:  # delivery-strategy selector
            return "auto-chain"
        if "stacked-to-main" in values:  # chain-strategy selector
            return "feature-branch-chain"
        return kw.get("default")  # flow-mode selector

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select),
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    # Chosen values echoed as this-run-only hints; config file byte-for-byte intact.
    assert "hybrid" in out
    assert "auto-chain" in out
    assert config_path.read_text(encoding="utf-8") == before


def test_preflight_chain_selector_skipped_for_single_pr(tmp_path: Path, capsys: Any) -> None:
    """Chain strategy is not asked when delivery is single-pr (no chaining)."""

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "ask-on-risk" in values:  # delivery-strategy selector
            return "single-pr"
        if "stacked-to-main" in values:  # chain-strategy selector — must NOT run
            raise AssertionError("chain-strategy selector must be skipped for single-pr")
        return kw.get("default")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select) as sel,
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    # flow mode + artifact store + delivery == three selectors, chain skipped.
    assert len(sel.call_args_list) == 3


def test_preflight_chain_selector_skipped_for_plan_only(tmp_path: Path, capsys: Any) -> None:
    """Chain strategy is not asked when delivery is plan-only (nothing to deliver)."""

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "ask-on-risk" in values:  # delivery-strategy selector
            return "plan-only"
        if "stacked-to-main" in values:  # chain-strategy selector — must NOT run
            raise AssertionError("chain-strategy selector must be skipped for plan-only")
        return kw.get("default")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select) as sel,
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    assert len(sel.call_args_list) == 3


def test_preflight_chain_selector_shown_when_delivery_chains(tmp_path: Path, capsys: Any) -> None:
    """Chain strategy IS asked when delivery may chain (e.g. auto-chain)."""
    seen: dict[str, bool] = {"chain": False}

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "ask-on-risk" in values:  # delivery-strategy selector
            return "auto-chain"
        if "stacked-to-main" in values:  # chain-strategy selector
            seen["chain"] = True
            assert set(values) >= {"stacked-to-main", "feature-branch-chain"}
            return kw.get("default")
        return kw.get("default")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select) as sel,
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    assert seen["chain"] is True
    assert len(sel.call_args_list) == 4


def test_preflight_mode_choice_applies_this_run_only(tmp_path: Path, capsys: Any) -> None:
    """Choosing stepwise applies to this run; opencontext.yaml is not written."""
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text("sdd:\n  flow_mode: automatic\n", encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "automatic" in values and "stepwise" in values:  # flow-mode selector
            return "stepwise"
        return kw.get("default")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select),
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    # stepwise pauses before the first phase -> request_approval.
    assert "request_approval" in out
    # Persistence hint printed; config untouched.
    assert "opencontext config set sdd.flow_mode stepwise" in out
    assert config_path.read_text(encoding="utf-8") == before


def test_preflight_skipped_for_json(tmp_path: Path, capsys: Any) -> None:
    """--json skips the preflight; stdout is pure JSON with the same shape."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select") as sel,
        patch("opencontext_core.prompts.confirm") as conf,
    ):
        handle_oc_new(_args(tmp_path, json_out=True))

    out = capsys.readouterr().out
    assert not sel.called and not conf.called
    data = json.loads(out)
    assert data["schema_version"] == "opencontext.oc_new_state.v1"
    assert data["current_phase"] == "explore"


def test_preflight_skipped_for_yes_and_non_interactive(tmp_path: Path, capsys: Any) -> None:
    """--yes / --non-interactive start directly without prompting."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select") as sel,
        patch("opencontext_core.prompts.confirm") as conf,
    ):
        handle_oc_new(_args(tmp_path, yes=True))
        handle_oc_new(_args(tmp_path, task="second task", non_interactive=True))

    out = capsys.readouterr().out
    assert not sel.called and not conf.called
    assert "spawn_subagent" in out


def test_preflight_skipped_without_tty(tmp_path: Path, capsys: Any) -> None:
    """Non-TTY behaves exactly like today: no prompt, run starts."""
    with (
        _tty(False),
        patch("opencontext_core.prompts.select") as sel,
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    assert not sel.called
    assert "spawn_subagent" in out


def test_preflight_decline_starts_nothing(tmp_path: Path, capsys: Any) -> None:
    """Declining the confirmation leaves no run behind."""
    from opencontext_core.oc_new.store import OcNewStore

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_default_dispatch()),
        patch("opencontext_core.prompts.confirm", return_value=False),
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    assert "cancel" in out.lower()
    assert OcNewStore(tmp_path).list_runs() == []


def test_explicit_flow_flag_is_preflight_default(tmp_path: Path, capsys: Any) -> None:
    """--flow hybrid seeds the flow-mode selector; keeping it runs hybrid semantics."""

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        return kw.get("default")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select) as sel,
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path, flow="hybrid"))

    # The flow-mode selector (the one offering automatic/stepwise/hybrid) is
    # seeded with the --flow value; other selectors have their own defaults.
    flow_calls = [
        call
        for call in sel.call_args_list
        if any(
            (c[0] if isinstance(c, tuple) else c) == "stepwise"
            for c in (call.args[1] if len(call.args) > 1 else call.kwargs["choices"])
        )
    ]
    assert flow_calls, "flow-mode selector must be invoked"
    assert flow_calls[0].kwargs.get("default") == "hybrid"


def _first_handoff_choices(tmp_path: Path) -> dict:
    """Load the persisted run and return the first handoff's session_choices block."""
    from opencontext_core.oc_new.store import OcNewStore

    runs = OcNewStore(tmp_path).list_runs()
    assert runs, "expected a run to have started"
    na = runs[0].next_action
    assert na is not None and na.kind == "spawn_subagent"
    return na.metadata["session_choices"]


def test_preflight_choices_reach_the_agent_handoff(tmp_path: Path, capsys: Any) -> None:
    """Choices picked in the preflight ride the conductor's agent-facing handoff."""

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "hybrid" in values and "engram" in values:  # artifact-store selector
            return "engram"
        if "ask-on-risk" in values:  # delivery-strategy selector
            return "auto-chain"
        if "stacked-to-main" in values:  # chain-strategy selector
            return "stacked-to-main"
        return kw.get("default")  # flow-mode selector (automatic)

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select),
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    block = _first_handoff_choices(tmp_path)
    assert block["artifact_store"] == "engram"
    assert block["delivery_strategy"] == "auto-chain"
    assert block["chain_strategy"] == "stacked-to-main"
    assert block["flow_mode"] == "automatic"


def test_handoff_uses_config_defaults_when_preflight_skipped(tmp_path: Path, capsys: Any) -> None:
    """--yes skips the preflight; the handoff still carries the config defaults."""
    (tmp_path / "opencontext.yaml").write_text(
        "sdd:\n"
        "  artifact_store:\n"
        "    mode: hybrid\n"
        "  delivery_strategy: ask-on-risk\n"
        "  chain_strategy: feature-branch-chain\n",
        encoding="utf-8",
    )
    before = (tmp_path / "opencontext.yaml").read_text(encoding="utf-8")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select") as sel,
        patch("opencontext_core.prompts.confirm") as conf,
    ):
        handle_oc_new(_args(tmp_path, yes=True))

    assert not sel.called and not conf.called
    block = _first_handoff_choices(tmp_path)
    # No interactive choices → every field defaults from the project's SDD config.
    assert block["artifact_store"] == "hybrid"
    assert block["delivery_strategy"] == "ask-on-risk"
    assert block["chain_strategy"] == "feature-branch-chain"
    # Config file untouched.
    assert (tmp_path / "opencontext.yaml").read_text(encoding="utf-8") == before


def test_preflight_choices_do_not_write_config_through_command(tmp_path: Path, capsys: Any) -> None:
    """Even when choices differ from config, the command never writes the file."""
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(
        "sdd:\n  flow_mode: automatic\n  delivery_strategy: plan-only\n",
        encoding="utf-8",
    )
    before = config_path.read_text(encoding="utf-8")

    def _select(message: str, choices: Any, **kw: Any) -> Any:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "hybrid" in values and "engram" in values:
            return "engram"
        if "ask-on-risk" in values:
            return "auto-chain"
        if "stacked-to-main" in values:
            return "feature-branch-chain"
        return kw.get("default")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", side_effect=_select),
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    block = _first_handoff_choices(tmp_path)
    assert block["artifact_store"] == "engram"
    assert block["delivery_strategy"] == "auto-chain"
    assert config_path.read_text(encoding="utf-8") == before
