# TUI screen modules.
from opencontext_cli.tui.screens.budget import BudgetScreen
from opencontext_cli.tui.screens.context import ContextViewerScreen
from opencontext_cli.tui.screens.harness import HarnessPanel
from opencontext_cli.tui.screens.learning_inbox import LearningInbox
from opencontext_cli.tui.screens.memory import MemoryBrowserScreen
from opencontext_cli.tui.screens.new_change import NewChangeScreen
from opencontext_cli.tui.screens.receipt import ReceiptViewer

# NOTE: the former install_wizard screen was a display-only mock (no choice
# handling, applied nothing) and was removed. `opencontext install` uses the
# framed prompt wizard (opencontext_core.dx.wizard_frame) instead.

__all__ = [
    "BudgetScreen",
    "ContextViewerScreen",
    "HarnessPanel",
    "LearningInbox",
    "MemoryBrowserScreen",
    "NewChangeScreen",
    "ReceiptViewer",
]
