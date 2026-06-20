"""Review CLI command — party mode multi-perspective code review."""

from __future__ import annotations

import os
from typing import Any

# Providers that never leave the machine — not gated as external sends.
_LOCAL_PROVIDERS = {"mock", "local"}


class ProviderBlockedError(RuntimeError):
    """Raised when an external review send is blocked by safety policy."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"External review send blocked: {reason}")


def guard_external_send(provider: str, content: str, *, config: Any | None = None) -> str:
    """Gate an external review send through firewall + provider policy + redaction.

    Returns the (redacted) payload safe to send when allowed. Raises
    :class:`ProviderBlockedError` when secure/air-gapped mode, provider policy,
    a disabled external-provider switch, or a raw secret blocks the send.

    Local providers (mock/local) are never treated as external sends and pass
    through unchanged. Before this guard existed, ``review --party`` sent code to
    external LLMs with no secure-mode, provider-policy, or redaction checks.
    """

    if provider in _LOCAL_PROVIDERS:
        return content

    from opencontext_core.config import load_config_or_defaults
    from opencontext_core.models.context import (
        ContextItem,
        ContextPriority,
        DataClassification,
    )
    from opencontext_core.safety.firewall import ContextFirewall
    from opencontext_core.safety.redaction import SinkGuard
    from opencontext_core.safety.secrets import SecretScanner

    cfg = config if config is not None else load_config_or_defaults()

    # A raw secret in the source must block the send outright — never sent, even
    # though redaction would mask it — so the policy decision is honest.
    if SecretScanner().scan(content):
        raise ProviderBlockedError("raw_secret_detected_before_provider_call")

    # Redact secrets/PII so the payload that crosses the boundary is sanitized.
    redacted, _ = SinkGuard().redact(content)

    item = ContextItem(
        id="review:context",
        content=redacted,
        source="review-cli",
        source_type="review",
        priority=ContextPriority.P1,
        tokens=max(1, len(redacted) // 4),
        score=1.0,
        classification=DataClassification.INTERNAL,
        redacted=True,
        metadata={"redacted": True},
    )

    decision = ContextFirewall(cfg).check_provider_call(
        provider,
        [item],
        provider_metadata=None,
    )
    if not decision.allowed:
        raise ProviderBlockedError(decision.reason)

    return redacted


PARTY_ROLES = {
    "architect": (
        "You are a Senior Software Architect with 15+ years of experience. "
        "Focus on: system design, coupling, cohesion, scalability, and architectural patterns. "
        "Identify structural issues, over-engineering, or missing abstractions. "
        "Be direct and specific."
    ),
    "security": (
        "You are a Security Specialist and AppSec engineer. "
        "Focus on: OWASP Top 10, injection risks, auth/authz gaps, secret leakage, "
        "insecure defaults, and supply-chain vulnerabilities. "
        "Flag anything that could be exploited."
    ),
    "performance": (
        "You are a Performance Engineer. "
        "Focus on: algorithmic complexity, unnecessary allocations, blocking I/O, "
        "missing caching, N+1 queries, and hot-path inefficiencies. "
        "Quantify impact where possible."
    ),
    "ux": (
        "You are a UX/DX Engineer focused on developer experience. "
        "Focus on: API ergonomics, error messages, CLI usability, documentation gaps, "
        "confusing naming, and friction in the developer workflow. "
        "Think about the first-time user experience."
    ),
}


def generate_role_prompt(role: str, context: str) -> str:
    """Generate a review prompt for the given role and context."""
    base = PARTY_ROLES.get(role, PARTY_ROLES["architect"])
    return (
        f"{base}\n\n"
        f"Review the following code/change and provide your findings as a JSON object with:\n"
        f"- role: '{role}'\n"
        f"- findings: list of {{severity: 'high'|'medium'|'low', title: str, details: str}}\n"
        f"- summary: one-sentence verdict\n\n"
        f"Context:\n{context}"
    )


def merge_reports(reports: list[dict[str, Any]]) -> str:
    """Merge findings from multiple role reports into a unified markdown report."""
    lines = [
        "# Party Mode Review Report",
        "",
        f"**Reviewers**: {', '.join(r.get('role', '?') for r in reports)}",
        "",
    ]

    by_severity: dict[str, list[dict[str, Any]]] = {"high": [], "medium": [], "low": []}

    for report in reports:
        role = report.get("role", "unknown")
        for finding in report.get("findings", []):
            severity = finding.get("severity", "low").lower()
            if severity not in by_severity:
                severity = "low"
            by_severity[severity].append(
                {
                    "role": role,
                    "title": finding.get("title", ""),
                    "details": finding.get("details", ""),
                }
            )

    for severity in ("high", "medium", "low"):
        items = by_severity[severity]
        if not items:
            continue
        lines.append(f"## {severity.capitalize()} Severity ({len(items)})")
        lines.append("")
        for item in items:
            lines.append(f"### [{item['role']}] {item['title']}")
            lines.append(item["details"])
            lines.append("")

    lines.append("## Summaries")
    lines.append("")
    for report in reports:
        role = report.get("role", "unknown")
        summary = report.get("summary", "No summary.")
        lines.append(f"**{role.title()}**: {summary}")
    lines.append("")

    total = sum(len(items) for items in by_severity.values())
    lines.append(f"*Total findings: {total}*")

    return "\n".join(lines)


def add_review_parser(subparsers: Any) -> None:
    """Add review command parser."""
    review_parser = subparsers.add_parser(
        "review",
        help="Multi-perspective code review (party mode).",
    )
    review_parser.add_argument(
        "--party",
        action="store_true",
        help="Run party mode: spawn independent reviewers with different role perspectives.",
    )
    review_parser.add_argument(
        "--roles",
        default="architect,security,performance,ux",
        help="Comma-separated roles (default: all 4).",
    )
    review_parser.add_argument(
        "--context",
        default=None,
        help="Code or change context to review. Reads stdin if omitted.",
    )
    review_parser.add_argument(
        "--output",
        default=None,
        help="Write merged report to this file.",
    )


def handle_review(args: Any) -> None:
    """Handle review command."""
    import sys

    from rich.console import Console as RichConsole
    from rich.status import Status

    rich_console = RichConsole()

    # Party mode is the only review mode, so it is the default. --party is still
    # accepted (no-op) for back-compat; previously its absence made the command a
    # silent no-op that read and discarded stdin.
    roles = [
        r.strip() for r in getattr(args, "roles", "architect,security,performance,ux").split(",")
    ]
    context = getattr(args, "context", None) or sys.stdin.read()
    output_path = getattr(args, "output", None)

    if not context.strip():
        rich_console.print("[red]No context provided for review.[/]")
        return

    rich_console.print(f"[bold]Party Mode Review[/] — {len(roles)} independent reviewers")

    from opencontext_core.config import load_config_or_defaults

    config = load_config_or_defaults()

    reports: list[dict[str, Any]] = []

    with Status("[bold green]Spawning reviewers...", console=rich_console):
        for role in roles:
            prompt = generate_role_prompt(role, context)
            report = _run_reviewer(role, prompt, context=context, config=config)
            reports.append(report)
            rich_console.print(
                f"  [green]✓[/] {role}: {len(report.get('findings', []))} finding(s)"
            )

    merged = merge_reports(reports)

    if output_path:
        from pathlib import Path

        Path(output_path).write_text(merged, encoding="utf-8")
        rich_console.print(f"[green]Report written to {output_path}[/]")
    else:
        rich_console.print(merged)


def _get_adapter() -> tuple[Any, str] | None:
    """Return (adapter, provider_name) for the first available provider, or None."""
    from opencontext_core.providers.adapters import (
        AnthropicAdapter,
        OpenRouterAdapter,
        ProviderConfig,
    )

    if os.environ.get("ANTHROPIC_API_KEY"):
        return (
            AnthropicAdapter(
                ProviderConfig(name="anthropic", api_key=os.environ["ANTHROPIC_API_KEY"])
            ),
            "anthropic",
        )
    if os.environ.get("OPENROUTER_API_KEY"):
        return (
            OpenRouterAdapter(
                ProviderConfig(name="openrouter", api_key=os.environ["OPENROUTER_API_KEY"])
            ),
            "openrouter",
        )
    return None


def _run_reviewer(
    role: str,
    prompt: str,
    *,
    context: str | None = None,
    config: Any | None = None,
) -> dict[str, Any]:
    """Run a single reviewer via LLM if a provider is configured.

    Returns a dict with role, findings, and summary keys.
    Falls back to a scaffold result when no provider is available. Every
    external send is gated through :func:`guard_external_send` (firewall +
    provider policy + redaction); a blocked send is reported, never silently
    sent.
    """
    selected = _get_adapter()
    if selected is None:
        return {
            "role": role,
            "findings": [],
            "summary": f"{role.title()} review: LLM provider not configured. "
            "Set a provider in your opencontext config to enable automated review.",
        }

    adapter, provider = selected

    # Fail-closed safety gate before any external send.
    try:
        guard_external_send(provider, context if context is not None else prompt, config=config)
    except ProviderBlockedError as exc:
        return {
            "role": role,
            "findings": [],
            "summary": f"{role.title()} review blocked by policy: {exc.reason}",
        }

    try:
        response = adapter.chat([{"role": "user", "content": prompt}])
        import json

        data: dict[str, Any] = json.loads(response.content)
        if not all(k in data for k in ("role", "findings", "summary")):
            raise ValueError("Response missing required keys: role, findings, summary")
        return data
    except Exception as exc:
        return {
            "role": role,
            "findings": [],
            "summary": f"{role.title()} review failed: {exc}",
        }
