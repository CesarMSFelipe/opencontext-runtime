"""AICXRenderer: ContextBytecode → human-readable or JSON-compact text."""

from __future__ import annotations

import json

from opencontext_core.context.bytecode.models import ContextBytecode


class AICXRenderer:
    """Renders bytecode. Two modes: text (debug/CLI) and json (transport)."""

    def render_text(self, bc: ContextBytecode) -> str:
        lines = [bc.version]
        for instr in bc.instructions:
            parts = [instr.op, *instr.args]
            lines.append(" ".join(parts))
        lines.append(f"CHK {bc.checksum}")
        return "\n".join(lines)

    def render_json(self, bc: ContextBytecode) -> str:
        return json.dumps(
            {
                "v": bc.version,
                "r": bc.request_id,
                "d": bc.dictionary,
                "i": [[instr.op, *instr.args] for instr in bc.instructions],
                "chk": bc.checksum,
            },
            separators=(",", ":"),
        )

    def render_compact(self, bc: ContextBytecode) -> dict:
        """Return Python dict suitable for inter-agent transport (no JSON serialization cost)."""
        return {
            "v": bc.version,
            "r": bc.request_id,
            "d": bc.dictionary,
            "i": [[instr.op, *instr.args] for instr in bc.instructions],
            "chk": bc.checksum,
        }
