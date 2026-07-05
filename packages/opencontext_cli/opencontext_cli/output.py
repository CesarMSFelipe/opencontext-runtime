"""Unified output-mode resolver and renderer (PR-013, SPEC-CLI-013-11).

A single place that maps ``--output {human|json|yaml|quiet|verbose}`` (with
``--json`` / ``OPENCONTEXT_JSON`` honoured as aliases of ``json``) onto one enum,
and renders a contract dict accordingly. The new PR-013 commands
(``simulate`` / ``session`` / ``workflow explain`` / ``profile explain`` /
``maturity`` / ``config doctor``) render through this so output stays consistent
without retrofitting every legacy command's bespoke ``--json`` flag.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from enum import StrEnum
from typing import Any

_FALSEY = {"", "0", "false", "no", "off"}

OUTPUT_CHOICES = ("human", "json", "yaml", "quiet", "verbose")


class OutputMode(StrEnum):
    human = "human"
    json = "json"
    yaml = "yaml"
    quiet = "quiet"
    verbose = "verbose"


def add_output_flag(parser: Any) -> None:
    """Add the standard ``--output`` mode flag to *parser*."""
    parser.add_argument(
        "--output",
        choices=list(OUTPUT_CHOICES),
        default=None,
        help="Output mode (human|json|yaml|quiet|verbose). Default human; --json == json.",
    )


def resolve_output_mode(args: Any) -> OutputMode:
    """Resolve the effective output mode from args/env (json/human aliases)."""
    explicit = getattr(args, "output", None)
    if explicit in OUTPUT_CHOICES:
        return OutputMode(explicit)
    if getattr(args, "json", False):
        return OutputMode.json
    if getattr(args, "json_out", False):
        return OutputMode.json
    env = os.environ.get("OPENCONTEXT_JSON")
    if env is not None and env.strip().lower() not in _FALSEY:
        return OutputMode.json
    return OutputMode.human


def envelope(schema: str, data: dict[str, Any]) -> dict[str, Any]:
    """Prepend the ``schema`` discriminator to a machine-facing payload.

    The machine-readable family (``status`` / ``install`` / ``memory`` /
    ``explain`` / ``config show`` …) all emit a top-level ``schema`` key so a
    consumer can tell what it is parsing. This is the single home for that
    convention so the key name/placement cannot drift.

    Deliberately NOT a wrapping envelope: it merges ``schema`` into the payload
    rather than nesting under ``data``. Existing consumers read specific keys, so
    an extra top-level key is additive; a wrapper would be a breaking change.
    ``schema`` wins on collision — a payload cannot spoof its own discriminator.
    """
    return {**data, "schema": schema}


def eprint(message: str) -> None:
    """Print a branded error line to *stderr* (brand palette, CI-safe).

    Diagnostics must never pollute the ``--json`` stdout stream, so error text
    goes to stderr through a stderr-bound console. Callers decide the exit code
    (``return 1`` for exit-code handlers, ``sys.exit(1)`` otherwise).
    """
    try:
        from rich.console import Console

        from opencontext_core.dx.console_styles import BRAND_ERROR

        Console(stderr=True).print(f"[bold {BRAND_ERROR}]✗[/] {message}")
    except Exception:  # rich missing / unusable — still emit on stderr.
        import sys

        print(f"x {message}", file=sys.stderr)


def emit(
    data: dict[str, Any],
    mode: OutputMode,
    human: Callable[[dict[str, Any]], None],
    *,
    verbose: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Render *data* per *mode*. ``human`` renders the default/verbose view."""
    if mode is OutputMode.quiet:
        return
    if mode is OutputMode.json:
        print(json.dumps(data, indent=2, default=str))
        return
    if mode is OutputMode.yaml:
        import yaml

        print(yaml.safe_dump(data, sort_keys=False))
        return
    if mode is OutputMode.verbose and verbose is not None:
        verbose(data)
        return
    human(data)
