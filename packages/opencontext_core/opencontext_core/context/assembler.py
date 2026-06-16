"""Prompt assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.context.prompt_cache import PromptPrefixCachePlanner
from opencontext_core.models.context import (
    AssembledPrompt,
    ContextItem,
    ContextPriority,
    PromptSection,
)
from opencontext_core.safety.prompt_injection import (
    PromptInjectionScanner,
    render_untrusted_context,
)
from opencontext_core.safety.redaction import SinkGuard

if TYPE_CHECKING:
    from opencontext_core.rules.loader import ResolvedRules


class PromptAssembler:
    """Builds a deterministic prompt from request and selected context."""

    def assemble(
        self,
        user_request: str,
        context_items: list[ContextItem],
        *,
        instructions: str = "",
        tool_schemas: str = "",
        provider_policy_summary: str = "",
        project_manifest: str = "",
        repo_map: str = "",
        workflow_contract: str = "",
        memory: str = "",
        conversation: str = "",
        rules: ResolvedRules | None = None,
    ) -> AssembledPrompt:
        """Assemble a prompt with traceable sections.

        When ``rules`` carries resolved developer-authored rules, a dedicated
        high-priority, trusted ``rules`` section is injected so conventions,
        personas, and output styles reach the model. The section is additive and
        gated: callers that do not pass ``rules`` (or pass an empty set) get the
        exact same sections as before, preserving backward compatibility.
        """

        context_lines = []
        scanner = PromptInjectionScanner()
        sink_guard = SinkGuard()
        safe_user_request, user_redacted = sink_guard.redact(user_request)
        user_findings = scanner.scan(safe_user_request)
        if user_findings:
            safe_user_request = f"[INJECTION_WARNING:{len(user_findings)}]\n{safe_user_request}"
        for index, item in enumerate(context_items, start=1):
            redacted_content, redacted = sink_guard.redact(item.content)
            rendered_content = render_untrusted_context(
                item.source,
                item.classification.value,
                redacted_content,
            )
            findings = scanner.scan(redacted_content)
            if findings:
                rendered_content = f"[INJECTION_WARNING:{len(findings)}]\n{rendered_content}"
            context_lines.append(
                "\n".join(
                    [
                        f"[{index}] source={item.source} type={item.source_type} "
                        f"priority={item.priority.name} score={item.score:.4f} redacted={redacted}",
                        rendered_content,
                    ]
                )
            )
        context_content, retrieved_redacted = sink_guard.redact(
            "\n\n".join(context_lines) if context_lines else "No project context selected."
        )
        rules_section = _build_rules_section(sink_guard, rules)
        sections = [
            _section(
                sink_guard,
                name="system",
                content=(
                    "You are using OpenContext Runtime. Answer from selected context, "
                    "state uncertainty, and avoid inventing project facts."
                ),
                stable=True,
                priority=ContextPriority.P0,
                trusted=True,
            ),
            _section(
                sink_guard,
                name="instructions",
                content=instructions or "No additional trusted instructions selected.",
                stable=True,
                priority=ContextPriority.P1,
                trusted=True,
            ),
            _section(
                sink_guard,
                name="tool_schemas",
                content=tool_schemas or "No tool schemas enabled.",
                stable=True,
                priority=ContextPriority.P1,
                trusted=True,
            ),
            _section(
                sink_guard,
                name="provider_policy_summary",
                content=provider_policy_summary or "Provider policy: mock/local only by default.",
                stable=True,
                priority=ContextPriority.P1,
                trusted=True,
            ),
            _section(
                sink_guard,
                name="project_manifest",
                content=project_manifest or "Project manifest summary unavailable.",
                stable=True,
                priority=ContextPriority.P1,
                trusted=True,
            ),
            _section(
                sink_guard,
                name="repo_map",
                content=repo_map or "Repository map unavailable.",
                stable=True,
                priority=ContextPriority.P1,
                trusted=True,
            ),
            _section(
                sink_guard,
                name="workflow_contract",
                content=workflow_contract
                or "Use the selected context and explain uncertainty when evidence is missing.",
                stable=True,
                priority=ContextPriority.P1,
                trusted=True,
            ),
            _section(
                sink_guard,
                name="memory",
                content=memory or "No additional project memory selected.",
                stable=False,
                priority=ContextPriority.P2,
            ),
            PromptSection(
                name="retrieved_context",
                content=context_content,
                stable=False,
                tokens=0,
                priority=ContextPriority.P1,
                redacted=retrieved_redacted,
            ),
            _section(
                sink_guard,
                name="conversation",
                content=conversation or "No prior conversation provided.",
                stable=False,
                priority=ContextPriority.P3,
            ),
            PromptSection(
                name="current_user_input",
                content=safe_user_request,
                stable=False,
                tokens=0,
                priority=ContextPriority.P0,
                redacted=user_redacted,
            ),
        ]
        if rules_section is not None:
            # Inject the rules/persona section right after the instructions
            # section so it sits in the high-priority, trusted, cache-stable
            # prefix. Gated on non-empty resolved rules so callers that pass no
            # rules see exactly the legacy section set.
            sections.insert(2, rules_section)
        measured_sections = [
            section.model_copy(update={"tokens": estimate_tokens(section.content)})
            for section in sections
        ]
        measured_sections = PromptPrefixCachePlanner().order_sections(measured_sections)
        prompt = "\n\n".join(
            f"## {section.name.replace('_', ' ').title()}\n{section.content}"
            for section in measured_sections
        )
        return AssembledPrompt(
            content=prompt,
            sections=measured_sections,
            total_tokens=estimate_tokens(prompt),
        )


def _build_rules_section(
    sink_guard: SinkGuard, rules: ResolvedRules | None
) -> PromptSection | None:
    """Render resolved (winning) rules into a trusted, high-priority section.

    Returns ``None`` when there are no resolved rules so the section is omitted
    entirely (additive + backward compatible). Only applied rules are rendered;
    overridden rules are deliberately excluded so the prompt reflects exactly
    the winning layer, matching what the trace records as applied.
    """

    if rules is None or rules.is_empty():
        return None

    by_category: dict[str, list[str]] = {}
    source_ids: list[str] = []
    for rule in rules.applied:
        by_category.setdefault(rule.category, []).append(rule.content)
        source_ids.append(f"{rule.layer}:{rule.category}:{rule.key}")

    lines: list[str] = [
        "Developer-authored project rules (trusted; follow these conventions):",
    ]
    for category in sorted(by_category):
        lines.append(f"\n{category.title()}:")
        for content in by_category[category]:
            lines.append(f"  - {content}")
    rendered = "\n".join(lines)

    safe_content, redacted = sink_guard.redact(rendered)
    return PromptSection(
        name="rules",
        content=safe_content,
        stable=True,
        tokens=0,
        priority=ContextPriority.P1,
        trusted=True,
        redacted=redacted,
        source_ids=source_ids,
    )


def _section(
    sink_guard: SinkGuard,
    *,
    name: str,
    content: str,
    stable: bool,
    priority: ContextPriority,
    trusted: bool = False,
) -> PromptSection:
    safe_content, redacted = sink_guard.redact(content)
    return PromptSection(
        name=name,
        content=safe_content,
        stable=stable,
        tokens=0,
        priority=priority,
        trusted=trusted,
        redacted=redacted,
    )
