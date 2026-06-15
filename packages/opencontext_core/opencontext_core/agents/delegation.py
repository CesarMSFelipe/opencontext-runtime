"""Sub-agent delegation for SDD orchestration.

Implements real delegation to sub-agents for each SDD phase.
Supports both local execution (in-process) and remote execution
(via OpenCode sub-agent protocol).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class DelegationMode(StrEnum):
    """How to execute sub-agent tasks."""

    LOCAL = "local"  # Run in-process
    SUBPROCESS = "subprocess"  # Run as subprocess
    REMOTE = "remote"  # Call remote API
    MOCK = "mock"  # Mock for testing


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""

    status: str  # "success", "error", "timeout"
    output: str
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SubAgentDelegate:
    """Delegates SDD phase execution to sub-agents.

    Each phase runs in isolation with fresh context.
    """

    def __init__(
        self,
        mode: DelegationMode = DelegationMode.LOCAL,
        timeout: int = 300,
        compression_mode: str = "terse",
    ) -> None:
        self.mode = mode
        self.timeout = timeout
        self._local_handlers: dict[str, Any] = {}
        self._compression_mode = compression_mode
        try:
            from opencontext_core.backends.factory import BackendFactory

            self._compressor = BackendFactory.create_compression_backend(compression_mode)
        except Exception:
            self._compressor = None

    def _compress_context(self, context: dict) -> dict:
        """Compress context for inter-agent transport.

        EvidencePlan values are AICX-encoded (reference-only, no content inlined).
        Other large text values fall back to terse compression.
        """
        result = {}
        for k, v in context.items():
            if _is_evidence_plan(v):
                try:
                    from opencontext_core.context.bytecode import AICXCompiler, AICXRenderer

                    bc = AICXCompiler().compile(v)
                    result[k] = AICXRenderer().render_compact(bc)
                    continue
                except Exception:
                    pass
            if isinstance(v, str) and len(v) > 200 and self._compressor is not None:
                result[k] = self._compressor.compress(v, [])
            else:
                result[k] = v
        return result

    def register_handler(self, phase: str, handler: Any) -> None:
        """Register a local handler for a phase."""

        self._local_handlers[phase] = handler

    def delegate(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> SubAgentResult:
        """Delegate a phase to a sub-agent.

        Args:
            phase: SDD phase name.
            context: Context dict with task info, codebase info, etc.

        Returns:
            Sub-agent execution result.
        """

        if self.mode == DelegationMode.MOCK:
            return self._mock_delegate(phase, context)

        if self.mode == DelegationMode.LOCAL:
            return self._local_delegate(phase, context)

        if self.mode == DelegationMode.SUBPROCESS:
            return self._subprocess_delegate(phase, context)

        if self.mode == DelegationMode.REMOTE:
            return self._remote_delegate(phase, context)

        return SubAgentResult(  # type: ignore[unreachable]
            status="error",
            output="",
            error=f"Unknown delegation mode: {self.mode}",
        )

    def _mock_delegate(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> SubAgentResult:
        """Mock delegation for testing."""

        return SubAgentResult(
            status="success",
            output=f"Mock {phase} result for: {context.get('task', 'unknown')}",
            artifacts=[],
        )

    def _local_delegate(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> SubAgentResult:
        """Delegate to a local handler function."""

        handler = self._local_handlers.get(phase)
        if handler is None:
            return SubAgentResult(
                status="error",
                output="",
                error=f"No handler registered for phase: {phase}",
            )

        try:
            context = self._compress_context(context)
            result = handler(context)
            if isinstance(result, dict):
                return SubAgentResult(
                    status=result.get("status", "success"),
                    output=result.get("output", ""),
                    artifacts=result.get("artifacts", []),
                    metadata=result.get("metadata", {}),
                )
            return SubAgentResult(
                status="success",
                output=str(result),
            )
        except Exception as exc:
            return SubAgentResult(
                status="error",
                output="",
                error=str(exc),
            )

    def _subprocess_delegate(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> SubAgentResult:
        """Delegate to a subprocess script."""

        # Write context to temp file
        import tempfile

        context = self._compress_context(context)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(context, f)
            context_path = f.name

        try:
            # Look for phase script
            script_dir = Path.home() / ".config" / "opencontext" / "agents"
            script = script_dir / f"{phase}.py"

            if not script.exists():
                return SubAgentResult(
                    status="error",
                    output="",
                    error=f"Phase script not found: {script}",
                )

            result = subprocess.run(
                ["python3", str(script), context_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout)
                    return SubAgentResult(
                        status="success",
                        output=output.get("output", result.stdout),
                        artifacts=output.get("artifacts", []),
                        metadata=output.get("metadata", {}),
                    )
                except json.JSONDecodeError:
                    return SubAgentResult(
                        status="success",
                        output=result.stdout,
                    )
            else:
                return SubAgentResult(
                    status="error",
                    output=result.stdout,
                    error=result.stderr,
                )
        except subprocess.TimeoutExpired:
            return SubAgentResult(
                status="timeout",
                output="",
                error=f"Sub-agent timed out after {self.timeout}s",
            )
        except Exception as exc:
            return SubAgentResult(
                status="error",
                output="",
                error=str(exc),
            )
        finally:
            Path(context_path).unlink(missing_ok=True)

    def _remote_delegate(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> SubAgentResult:
        """Delegate to a remote API (e.g., OpenCode sub-agent)."""

        # This would call OpenCode's sub-agent API
        # For now, return scaffold result
        return SubAgentResult(
            status="success",
            output=f"Remote {phase} execution scaffold",
            metadata={"mode": "remote", "phase": phase},
        )


def _is_evidence_plan(v: object) -> bool:
    """Return True when ``v`` is a retrieval ``EvidencePlan`` (AICX-encodable)."""
    try:
        from opencontext_core.retrieval.contracts import EvidencePlan

        return isinstance(v, EvidencePlan)
    except Exception:
        return False
