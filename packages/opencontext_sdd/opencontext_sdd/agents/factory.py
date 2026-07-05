"""opencontext_sdd.agents.factory -- ``build_adapter(name) -> Adapter``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opencontext_sdd.agents.registry import ADAPTERS

if TYPE_CHECKING:
    from opencontext_sdd.agents.interface import Adapter


class UnknownAdapter(KeyError):
    """Raised when ``build_adapter`` is called with an unregistered name."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.adapter_name = name


def build_adapter(name: str) -> Adapter:
    """Construct a fresh ``Adapter`` for ``name``; raise ``UnknownAdapter`` if absent."""
    cls = ADAPTERS.get(name)
    if cls is None:
        raise UnknownAdapter(name)
    return cls()


__all__ = ["UnknownAdapter", "build_adapter"]
