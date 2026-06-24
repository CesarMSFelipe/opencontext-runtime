"""TaskQualityGate — verify task entry links a file path and a req ref.

A task entry is a dict that must contain at least one path-like ``files``
string and at least one ``REQ-N`` reference under ``requirements``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from opencontext_core.harness.models import GateStatus
from opencontext_core.sdd.requirements_gate import GateResult

_REQ_TOKEN_RE = re.compile(r"REQ-?\d+", re.IGNORECASE)


class TaskQualityGate:
    """Validate task entry references both a file path and a requirement id."""

    id = "task_quality"

    def evaluate(self, task_entry: dict[str, Any]) -> GateResult:
        errors: list[str] = []

        path = self._first_path(task_entry.get("files"))
        if not path:
            errors.append("task missing at least one file path under 'files'")

        ref = self._first_req_ref(task_entry.get("requirements"))
        if not ref:
            errors.append("task missing at least one REQ-N reference under 'requirements'")

        status = GateStatus.PASSED if not errors else GateStatus.FAILED
        return GateResult(status=status, errors=errors)

    @staticmethod
    def _first_path(value: Any) -> str | None:
        for item in TaskQualityGate._iter_strings(value):
            if "/" in item or "\\" in item or "." in item.split("/")[-1]:
                return str(item)
        return None

    @staticmethod
    def _first_req_ref(value: Any) -> str | None:
        for item in TaskQualityGate._iter_strings(value):
            if _REQ_TOKEN_RE.search(str(item)):
                return str(item)
        return None

    @staticmethod
    def _iter_strings(value: Any) -> Iterator[str]:
        if value is None:
            return
        if isinstance(value, str):
            yield value
            return
        if isinstance(value, (list, tuple, set)):
            for v in value:
                yield from TaskQualityGate._iter_strings(v)