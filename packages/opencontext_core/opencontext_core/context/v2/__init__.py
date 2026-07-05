"""OpenContext context v2 (PR-011 / SPEC §3.2 context).

Public surface for the L2 context-envelope layer: ranking, routing,
compression, usefulness, and envelope. The context v2 module is the
L2 substrate the higher layers (graph, memory, learning) consume.
"""

from __future__ import annotations

__capability__ = "context.v2"
