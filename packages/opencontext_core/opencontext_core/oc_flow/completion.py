"""OC Flow completion-status state machine (B1 / AVH-011, design ADR-A1).

The OC Flow graph reaching its terminal ``completed`` node is NOT, on its own,
proof that a mutation task was actually done. The audit observed a mutation task
finishing ``status: completed`` with ``changed_files: []`` and the bug intact — a
false pass. This module is the post-graph honesty gate that refuses that outcome.

``resolve_completion`` is called once, AFTER the graph terminates, and maps the raw
graph status onto a richer :class:`CompletionStatus`:

* a **read-only** task (docs / analysis / explain / review) MAY complete with no
  edits — a no-op is legitimate there;
* a **mutation-required** task may only be ``completed`` when it produced edits AND
  local inspection passed — otherwise it is reported honestly as
  ``needs_executor`` / ``needs_provider`` / ``escalated`` / ``blocked``.

Layering (doc 58): L9, importing only the sibling OC Flow nodes (L9) downward.
"""

from __future__ import annotations

from opencontext_core.compat import StrEnum
from opencontext_core.oc_flow.nodes import DeterministicNodeExecutor, OCFlowContext


class CompletionStatus(StrEnum):
    """The honest terminal status of an OC Flow run (ADR-A1)."""

    completed = "completed"
    blocked = "blocked"
    needs_executor = "needs_executor"
    needs_provider = "needs_provider"
    needs_verification = "needs_verification"
    needs_user_edit = "needs_user_edit"
    escalated = "escalated"


# Verbs that imply a code/file mutation (OC Flow's reason to exist).
_MUTATION_VERBS: tuple[str, ...] = (
    "fix",
    "implement",
    "refactor",
    "edit",
    "add",
    "create",
    "build",
    "introduce",
    "rename",
    "patch",
    "correct",
    "repair",
    "change",
    "modify",
    "update",
    "remove",
    "delete",
    "migrate",
    "rewrite",
    "resolve",
    "make",
    "optimize",
    "improve",
    "replace",
    "apply",
    "convert",
    "wire",
    "hook",
)

# Verbs that imply a read-only / analysis / documentation task — a no-op is honest.
_READONLY_VERBS: tuple[str, ...] = (
    "explain",
    "review",
    "analyze",
    "analyse",
    "describe",
    "summarize",
    "summarise",
    "audit",
    "investigate",
    "understand",
    "inspect",
    "report",
    "document",
    "docs",
    "readme",
    "comment",
    "outline",
    "list",
    "show",
    "what",
    "why",
    "how",
)


def mutation_required(task: str) -> bool:
    """Classify whether ``task`` requires a real code/file change (B1).

    Mutation verbs (fix / implement / refactor / edit / ...) win whenever present,
    so an audit case like "Fix failing test" is mutation-required even though it
    also mentions a "test". A read-only verb (explain / review / analyze / docs /
    ...) marks the task as no-op-permissible only when NO mutation verb is present.

    When neither signal is present the task is treated as mutation-required — the
    conservative side, so an ambiguous OC Flow task can never falsely report
    ``completed`` after producing nothing (audit honesty rule #1).
    """
    lowered = task.lower()
    if any(verb in lowered for verb in _MUTATION_VERBS):
        return True
    if any(verb in lowered for verb in _READONLY_VERBS):
        return False
    return True


def verification_required(task: str) -> bool:
    """Return whether success requires a real test/check command."""
    lowered = task.lower()
    return "test" in lowered or "pytest" in lowered or "failing" in lowered


def resolve_completion(
    graph_status: str,
    ctx: OCFlowContext,
    *,
    mutation_required: bool,
    provider_available: bool,
    verification_required: bool = False,
) -> CompletionStatus:
    """Map the raw graph status onto an honest :class:`CompletionStatus` (ADR-A1).

    ``graph_status`` is the runner's traversal verdict (``completed`` / ``escalated``
    / ``failed``). The state machine:

    * read-only task → honour the graph verdict (a no-op may ``complete``);
    * mutation task with verified edits (changed files AND inspection passed) →
      ``completed``;
    * mutation task that produced NOTHING → ``needs_executor`` (no model to mutate),
      ``needs_provider`` (provider-backed but unavailable) or ``blocked``;
    * mutation task that produced edits but could not verify them → ``escalated`` /
      ``blocked``.
    """
    if not mutation_required:
        if graph_status == "escalated":
            return CompletionStatus.escalated
        if graph_status == "completed":
            return CompletionStatus.completed
        return CompletionStatus.blocked

    verified = (
        bool(ctx.changed_files)
        and ctx.inspection is not None
        and ctx.inspection.outcome == "passed"
    )
    if verified and graph_status == "completed":
        if (
            verification_required
            and getattr(ctx.inspection, "verification_outcome", "not_run") != "passed"
        ):
            return CompletionStatus.needs_verification
        return CompletionStatus.completed

    if not ctx.changed_files:
        # The run produced no edits at all for a task that demands a change.
        if isinstance(ctx.executor, DeterministicNodeExecutor):
            return CompletionStatus.needs_executor
        if not provider_available:
            return CompletionStatus.needs_provider
        return CompletionStatus.blocked

    # Edits were produced but local inspection did not confirm success.
    if graph_status == "escalated":
        return CompletionStatus.escalated
    return CompletionStatus.blocked


def completion_reason(status: CompletionStatus, *, mutation_required: bool) -> str:
    """A short, stable explanation for a non-``completed`` terminal status."""
    return {
        CompletionStatus.completed: (
            "mutation verified" if mutation_required else "read-only task completed"
        ),
        CompletionStatus.needs_executor: (
            "mutation task produced no edits and no productive executor was configured "
            "(provider-free DeterministicNodeExecutor)"
        ),
        CompletionStatus.needs_provider: (
            "mutation task produced no edits because no provider was available"
        ),
        CompletionStatus.needs_verification: (
            "mutation applied but no targeted verification passed"
        ),
        CompletionStatus.needs_user_edit: "edits are awaiting user approval",
        CompletionStatus.escalated: (
            "could not converge within OC Flow bounds; escalated for a deeper fix"
        ),
        CompletionStatus.blocked: ("mutation task could not be verified as successful"),
    }[status]
