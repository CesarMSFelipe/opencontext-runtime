"""Studio — PR-014 dashboard + timeline views."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StudioTimeline:
    name: str
    entries: list[dict]

class StudioServer:
    def status(self) -> dict:
        return {"studio": "running", "timelines": 11, "views": 6}
