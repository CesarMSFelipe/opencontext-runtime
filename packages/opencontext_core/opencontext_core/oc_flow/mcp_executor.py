"""MCP-sampling OC Flow executor."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from opencontext_core.agents.executor import ApplyEdit
from opencontext_core.llm.sampling_gateway import HostSampler, SamplingGateway
from opencontext_core.oc_flow.models import ContextEnvelope, TaskContract
from opencontext_core.oc_flow.nodes import McpSamplingNodeExecutor


class MCPSamplingNodeExecutor(McpSamplingNodeExecutor):
    """Use host MCP sampling, then the existing ApplyEdit pipeline."""

    def __init__(self, *, sampler: HostSampler, root: Path, model: str = "host-selected") -> None:
        super().__init__(gateway=SamplingGateway(sampler, model=model), root=root, model=model)

    def mutate(self, contract: TaskContract, envelope: ContextEnvelope) -> list[ApplyEdit]:
        edits = super().mutate(contract, envelope)
        if self.block_reason == "provider returned an unparseable or schema-invalid edit set":
            self.block_reason = "sampling response failed ApplyEdit contract validation"
        return edits


__all__: Sequence[str] = ("MCPSamplingNodeExecutor",)
