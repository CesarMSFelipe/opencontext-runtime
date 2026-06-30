"""Brand header layout: text must not enter the logo's interior gap."""

from __future__ import annotations

import re

from opencontext_cli.tui.brand import render_brand_header
from opencontext_core.dx.brand_state import RuntimeBrandState

_MARKUP = re.compile(r"\[[^\]]+\]")


def _plain(line: str) -> str:
    return _MARKUP.sub("", line)


def test_brand_header_text_column_is_stable() -> None:
    header = render_brand_header(
        RuntimeBrandState(
            project_name="requests",
            project_status="installed",
            files=37,
            symbols=764,
            kg_status="healthy",
            memory_backend="local",
            flow_mode="hybrid",
            run_label="no active run",
            phase_label="-",
            next_label="start new change",
        )
    )

    lines = [_plain(line) for line in header.splitlines()]
    assert lines[0].index("OpenContext") == lines[1].index("Project:")
    assert lines[1].index("Project:") == lines[2].index("KG:")
    assert lines[2].index("KG:") == lines[3].index("Run:")
