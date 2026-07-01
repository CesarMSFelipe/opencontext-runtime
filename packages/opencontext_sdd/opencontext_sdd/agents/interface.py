"""opencontext_sdd.agents.interface — Adapter interface contract.

Host-client adapters (``claude-code``, ``opencode``, ...) inherit
:class:`Adapter` and expose the nine required members enumerated in
:data:`REQUIRED_METHODS`. The base class is an ``ABC`` so it cannot be
instantiated directly; the registry in ``registry.py`` enumerates concrete
subclasses and ``factory.build_adapter`` constructs them by name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

REQUIRED_METHODS: tuple[str, ...] = (
    "id",
    "display_name",
    "config_paths",
    "install",
    "uninstall",
    "status",
    "sync_state",
    "apply",
    "verify",
)


class Adapter(ABC):
    """Abstract base for every host-client adapter.

    Subclasses MUST set ``id`` and SHOULD set ``display_name`` and
    ``config_paths``. The six abstract methods drive the SDD orchestrator
    and return ``dict`` so the contract stays duck-typed downstream.
    """

    id: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    config_paths: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def install(self) -> dict[str, Any]: ...
    @abstractmethod
    def uninstall(self) -> dict[str, Any]: ...
    @abstractmethod
    def status(self) -> dict[str, Any]: ...
    @abstractmethod
    def sync_state(self) -> dict[str, Any]: ...
    @abstractmethod
    def apply(self, change: str) -> dict[str, Any]: ...
    @abstractmethod
    def verify(self, change: str) -> dict[str, Any]: ...


__all__ = ["REQUIRED_METHODS", "Adapter"]
