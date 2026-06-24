"""capabilities — show the client capability matrix (Workstream L).

Usage:
  opencontext capabilities [--json]
  opencontext capabilities <agent_id> [--json]
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_core.configurator.capability import build_capability_matrix


def add_capabilities_parser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "capabilities", help="Show which agent clients support what (MCP, AGENTS.md, ...)."
    )
    p.add_argument("agent_id", nargs="?", default=None, help="Optional: one client to show.")
    p.add_argument("--json", action="store_true", help="JSON output.")


def handle_capabilities(args: Any) -> None:
    matrix = build_capability_matrix()
    agent_id = getattr(args, "agent_id", None)
    json_out = getattr(args, "json", False)

    if agent_id:
        client = matrix.get(agent_id)
        if client is None:
            print(f"Unknown client: {agent_id}", file=sys.stderr)
            sys.exit(1)
        if json_out:
            print(json.dumps(client.model_dump(), indent=2))
        else:
            for k, v in client.model_dump().items():
                print(f"{k}: {v}")
        return

    if json_out:
        print(json.dumps(matrix.model_dump(), indent=2))
        return

    from opencontext_core.dx.console_styles import console

    console.header(f"Client Capabilities ({len(matrix.clients)})")
    rows = [
        [
            c.agent_id,
            "yes" if c.mcp else "no",
            c.mcp_shape,
            "yes" if c.honors_agents_md else "no",
            c.instructions_scope,
        ]
        for c in matrix.clients
    ]
    console.table("", ["Client", "MCP", "MCP shape", "AGENTS.md", "Instr. scope"], rows)
