"""NewChangeScreen — modal for starting a new oc-new change from the cockpit.

Provides an Input for the objective and Select widgets for flow, memory,
openspec, and git mode. Empty objective prevents dismissal.
"""

from __future__ import annotations

from typing import Any, ClassVar

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.screen import ModalScreen
    from textual.widgets import Button, Input, Label, Select
except ImportError:
    # NOTE: If textual is not available, provide stubs so that import does not crash.
    ModalScreen = object  # type: ignore[assignment,misc]
    ComposeResult = Any  # type: ignore[assignment]
    Binding = object  # type: ignore[assignment]

_FLOW_OPTIONS = [
    ("automatic", "Automatic — fully automated flow"),
    ("stepwise", "Stepwise — pause after each phase"),
    ("hybrid", "Hybrid — pause before code phases"),
    ("observe_only", "Observe only — no code execution"),
]

_MEMORY_OPTIONS = [
    ("auto", "Auto — detect best backend"),
    ("engram", "Engram — persistent memory"),
    ("local", "Local — in-run memory only"),
    ("off", "Off — no memory"),
]

_OPENSPEC_OPTIONS = [
    ("full", "Full — all SDD artifacts"),
    ("minimal", "Minimal — essential artifacts"),
    ("off", "Off — no artifact persistence"),
]

_GIT_OPTIONS = [
    ("none", "None — no git operations"),
    ("single_pr", "Single PR — one branch + PR"),
    ("local_branch", "Local branch — commit, no push"),
    ("commit_only", "Commit only — commit, no PR"),
    ("per_task_prs", "Per-task PRs — one PR per task"),
]


class NewChangeScreen(ModalScreen):  # type: ignore[misc,valid-type]
    """Modal for configuring and starting a new oc-new change."""

    BINDINGS: ClassVar[list] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    NewChangeScreen {
        align: center middle;
    }
    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 1 2;
        width: 70;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }
    #objective-label { column-span: 2; }
    #objective { column-span: 2; }
    Label { height: 1; }
    #button-row { column-span: 2; align: right middle; height: 3; }
    """

    def compose(self) -> ComposeResult:
        from textual.containers import Grid, Horizontal

        with Grid(id="dialog"):
            yield Label("Start a new change", id="objective-label")
            yield Input(placeholder="Objective — describe what needs to change", id="objective")
            yield Label("Flow mode")
            yield Select(_FLOW_OPTIONS, value="stepwise", id="flow")
            yield Label("Memory mode")
            yield Select(_MEMORY_OPTIONS, value="auto", id="memory")
            yield Label("OpenSpec mode")
            yield Select(_OPENSPEC_OPTIONS, value="minimal", id="openspec")
            yield Label("Git mode")
            yield Select(_GIT_OPTIONS, value="none", id="git")
            with Horizontal(id="button-row"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Start", variant="primary", id="start")

    def on_button_pressed(self, event: Any) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "start":
            self._submit()

    def on_key(self, event: Any) -> None:
        if getattr(event, "key", None) == "enter":
            self._submit()

    def _submit(self) -> None:
        objective_widget = self.query_one("#objective", Input)
        objective = objective_widget.value.strip()
        if not objective:
            # NOTE: Do not dismiss when objective is empty.
            return

        flow_widget = self.query_one("#flow", Select)
        memory_widget = self.query_one("#memory", Select)
        openspec_widget = self.query_one("#openspec", Select)
        git_widget = self.query_one("#git", Select)

        self.dismiss(
            {
                "objective": objective,
                "flow": str(flow_widget.value),
                "memory": str(memory_widget.value),
                "openspec": str(openspec_widget.value),
                "git": str(git_widget.value),
            }
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
