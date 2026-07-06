"""Formal executor registry (plan doc 2 §14 / doc 1 §14, EXE tests).

Executor resolution used to be hardcoded inside ``oc_flow.cli._resolve_executor``
and the harness gateway resolution. This module formalizes it: every executor
the runtime can attach is declared as an :class:`ExecutorSpec` with HONEST
capability flags, and the resolution paths consult :func:`default_registry`
to build one. This is a formalization, not a behavior change — the builders
delegate to the exact same construction code the resolution paths used before,
so existing configs resolve identically.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# A builder receives the run root plus executor-specific kwargs and returns a
# NodeExecutor (duck-typed) or None when the executor is not configured/buildable.
ExecutorBuilder = Callable[..., Any]


@dataclass(frozen=True)
class ExecutorSpec:
    """Honest capability declaration for one executor id.

    Defaults are least-capability: an executor declares nothing it cannot do.
    ``can_mutate=False`` means the executor can never produce file edits on its
    own (EXE-001); ``can_run_commands=False`` means it never spawns shell
    commands itself (verification commands are run by the runner, not the
    executor).
    """

    id: str
    description: str = ""
    can_mutate: bool = False
    can_run_commands: bool = False
    requires_network: bool = False
    requires_approval: bool = False
    supported_tasks: tuple[str, ...] = ()
    supported_languages: tuple[str, ...] = ("*",)

    def to_dict(self) -> dict[str, Any]:
        """JSON-shaped view (tuples become lists) for CLI/report output."""
        return {
            "id": self.id,
            "description": self.description,
            "can_mutate": self.can_mutate,
            "can_run_commands": self.can_run_commands,
            "requires_network": self.requires_network,
            "requires_approval": self.requires_approval,
            "supported_tasks": list(self.supported_tasks),
            "supported_languages": list(self.supported_languages),
        }


@dataclass
class ExecutorRegistry:
    """Register/get/list executor specs plus their optional builders."""

    _specs: dict[str, ExecutorSpec] = field(default_factory=dict)
    _builders: dict[str, ExecutorBuilder] = field(default_factory=dict)

    def register(self, spec: ExecutorSpec, builder: ExecutorBuilder | None = None) -> None:
        """Register a spec (and optionally its builder). Duplicate ids are an error."""
        if spec.id in self._specs:
            raise ValueError(f"executor id already registered: {spec.id!r}")
        self._specs[spec.id] = spec
        if builder is not None:
            self._builders[spec.id] = builder

    def get(self, executor_id: str) -> ExecutorSpec | None:
        return self._specs.get(executor_id)

    def list(self) -> list[ExecutorSpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    def build(self, executor_id: str, *, root: Path, **kwargs: Any) -> Any:
        """Build the executor for ``executor_id`` or return ``None``.

        ``None`` means "declared but not configured/buildable here" (e.g. a
        ``test_stub`` id without the explicit opt-in config) — the caller falls
        back exactly as the pre-registry resolution did. Unknown ids raise
        ``KeyError`` so a typo never silently degrades to no executor.
        """
        if executor_id not in self._specs:
            raise KeyError(f"unknown executor id: {executor_id!r}")
        builder = self._builders.get(executor_id)
        if builder is None:
            return None
        return builder(root=root, **kwargs)


# ------------------------------------------------------------- built-in builders
# Builders import lazily so this module never drags oc_flow at import time
# (oc_flow.cli consults the registry — a top-level import would be circular).
def _build_none(*, root: Path, **_kw: Any) -> Any:
    from opencontext_core.oc_flow.nodes import DeterministicNodeExecutor

    return DeterministicNodeExecutor()


def _build_provider(*, root: Path, provider_name: str = "", model: str = "", **_kw: Any) -> Any:
    from opencontext_core.oc_flow.cli import _build_detected_provider_executor

    return _build_detected_provider_executor(root, provider_name, model)


def _build_mcp(*, root: Path, sampler: Any = None, **_kw: Any) -> Any:
    if sampler is None:
        from opencontext_core.llm.sampling_gateway import get_host_sampler

        sampler = get_host_sampler()
    if sampler is None:
        return None
    from opencontext_core.oc_flow.mcp_executor import MCPSamplingNodeExecutor

    return MCPSamplingNodeExecutor(sampler=sampler, root=root)


def _build_test_stub(*, root: Path, **_kw: Any) -> Any:
    from opencontext_core.oc_flow.cli import _resolve_test_stub_executor

    return _resolve_test_stub_executor(root)


def _build_patch(*, root: Path, **_kw: Any) -> Any:
    from opencontext_core.executors.patch import resolve_patch_executor

    return resolve_patch_executor(root)


_DEFAULT_REGISTRY: ExecutorRegistry | None = None


def default_registry() -> ExecutorRegistry:
    """The process-wide registry of built-in executors (cached singleton)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is not None:
        return _DEFAULT_REGISTRY
    registry = ExecutorRegistry()
    registry.register(
        ExecutorSpec(
            id="none",
            description=(
                "Model-free deterministic executor: applies caller-supplied edits "
                "only; never invents a mutation (mutation tasks report needs_executor)."
            ),
            can_mutate=False,
        ),
        builder=_build_none,
    )
    registry.register(
        ExecutorSpec(
            id="provider",
            description="LLM provider-backed executor (detected API key / configured model).",
            can_mutate=True,
            requires_network=True,
            supported_tasks=("mutation", "diagnosis"),
        ),
        builder=_build_provider,
    )
    registry.register(
        ExecutorSpec(
            id="mcp",
            description="Host MCP sampling executor (the client's model produces the edits).",
            can_mutate=True,
            supported_tasks=("mutation", "diagnosis"),
        ),
        builder=_build_mcp,
    )
    registry.register(
        ExecutorSpec(
            id="test_stub",
            description=(
                "TEST-ONLY deterministic gateway over a JSON edits_file "
                "(explicit `provider: test_stub` config; never a production fallback)."
            ),
            can_mutate=True,
            supported_tasks=("mutation",),
        ),
        builder=_build_test_stub,
    )
    registry.register(
        ExecutorSpec(
            id="patch",
            description=(
                "Unified-diff executor: applies a configured .patch/.diff file to the "
                "workspace through the normal validate/policy/verify pipeline (EXE-004)."
            ),
            can_mutate=True,
            supported_tasks=("mutation",),
        ),
        builder=_build_patch,
    )
    _DEFAULT_REGISTRY = registry
    return registry
