"""Skill v2 persona — declarative tool compatibility."""

from __future__ import annotations


class ToolNotAllowedError(PermissionError):
    """Raised when a persona tries to invoke a tool outside its allow-list."""


class Persona:
    """A named persona with a fixed tool allow-list.

    Persona decides which tools a skill (running under that persona) can
    invoke. ``check_tool`` raises :class:`ToolNotAllowedError` on a miss.
    """

    def __init__(self, name: str, allowed_tools: tuple[str, ...] = ()) -> None:
        self.name = name
        self._allowed: frozenset[str] = frozenset(allowed_tools)

    def check_tool(self, tool: str) -> None:
        if tool not in self._allowed:
            raise ToolNotAllowedError(f"persona {self.name!r} cannot use tool {tool!r}")

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return tuple(self._allowed)


__all__ = ["Persona", "ToolNotAllowedError"]
