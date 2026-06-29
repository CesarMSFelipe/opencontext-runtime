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
