"""Review CLI command — party mode multi-perspective code review."""

from __future__ import annotations

import os
from typing import Any

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

    if not getattr(args, "party", False):
        rich_console.print("[yellow]Use --party for party mode review.[/]")
        return

    roles = [
        r.strip() for r in getattr(args, "roles", "architect,security,performance,ux").split(",")
    ]
    context = getattr(args, "context", None) or sys.stdin.read()
    output_path = getattr(args, "output", None)

    if not context.strip():
        rich_console.print("[red]No context provided for review.[/]")
        return

    rich_console.print(f"[bold]Party Mode Review[/] — {len(roles)} independent reviewers")

    reports: list[dict[str, Any]] = []

    with Status("[bold green]Spawning reviewers...", console=rich_console):
        for role in roles:
            prompt = generate_role_prompt(role, context)
            report = _run_reviewer(role, prompt)
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


def _get_adapter() -> Any | None:
    """Return the first available LLM provider adapter, or None."""
    from opencontext_core.providers.adapters import (
        AnthropicAdapter,
        OpenRouterAdapter,
        ProviderConfig,
    )

    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicAdapter(
            ProviderConfig(name="anthropic", api_key=os.environ["ANTHROPIC_API_KEY"])
        )
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenRouterAdapter(
            ProviderConfig(name="openrouter", api_key=os.environ["OPENROUTER_API_KEY"])
        )
    return None


def _run_reviewer(role: str, prompt: str) -> dict[str, Any]:
    """Run a single reviewer via LLM if a provider is configured.

    Returns a dict with role, findings, and summary keys.
    Falls back to a scaffold result when no provider is available.
    """
    adapter = _get_adapter()
    if adapter is None:
        return {
            "role": role,
            "findings": [],
            "summary": f"{role.title()} review: LLM provider not configured. "
            "Set a provider in your opencontext config to enable automated review.",
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
