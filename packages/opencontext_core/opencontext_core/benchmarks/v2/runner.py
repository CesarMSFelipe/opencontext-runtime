"""PR-017 BenchmarkRunner — deterministic suite execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchmarkResult:
    name: str
    success: bool
    methodology_version: str
    detail: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkTask:
    name: str
    run: Callable[[], BenchmarkResult]


@dataclass
class BenchmarkRunner:
    """In-order runner. ``run_all()`` returns results in registration order."""

    _tasks: list[BenchmarkTask] = field(default_factory=list)

    def register(self, task: BenchmarkTask) -> None:
        self._tasks.append(task)

    def run_all(self) -> list[BenchmarkResult]:
        return [t.run() for t in self._tasks]