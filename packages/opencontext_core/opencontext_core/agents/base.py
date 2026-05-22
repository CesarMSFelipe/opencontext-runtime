"""Base agent class for OpenContext agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Agent configuration model."""

    name: str = Field(..., description="Agent name")
    type: str = Field(..., description="Agent type")
    enabled: bool = Field(default=True)
    objectives: list[str] = Field(default_factory=list)
    scope: Optional[dict[str, Any]] = Field(default=None)
    token_budget: dict[str, Any] = Field(default_factory=dict)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    provider: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    automation: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


@dataclass
class AgentMetadata:
    """Metadata about agent execution."""

    agent_name: str
    agent_type: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    tokens_used: int = 0
    tokens_max: int = 0
    duration_seconds: float = 0.0
    findings_count: int = 0
    status: str = "running"  # running, completed, failed


class BaseAgent(ABC):
    """Base class for all OpenContext agents."""

    def __init__(self, config: AgentConfig, project_root: Path):
        """Initialize agent.

        Args:
            config: Agent configuration
            project_root: Root directory of project being analyzed
        """
        self.config = config
        self.project_root = Path(project_root)
        self.metadata = AgentMetadata(
            agent_name=config.name,
            agent_type=config.type,
            started_at=datetime.now(),
        )

    @abstractmethod
    async def execute(self) -> dict[str, Any]:
        """Execute agent analysis.

        Returns:
            Dictionary with analysis results, findings, and metadata
        """
        pass

    async def run(self) -> dict[str, Any]:
        """Run agent with error handling and metadata tracking.

        Returns:
            Complete agent result with findings and metadata
        """
        try:
            result = await self.execute()
            self.metadata.completed_at = datetime.now()
            self.metadata.status = "completed"
            self.metadata.duration_seconds = (
                self.metadata.completed_at - self.metadata.started_at
            ).total_seconds()
            return {
                "status": "success",
                "findings": result.get("findings", []),
                "metadata": {
                    "name": self.metadata.agent_name,
                    "type": self.metadata.agent_type,
                    "started_at": self.metadata.started_at.isoformat(),
                    "completed_at": self.metadata.completed_at.isoformat(),
                    "duration_seconds": self.metadata.duration_seconds,
                    "tokens_used": self.metadata.tokens_used,
                    "findings_count": len(result.get("findings", [])),
                },
                **result,
            }
        except Exception as e:
            self.metadata.status = "failed"
            self.metadata.completed_at = datetime.now()
            return {
                "status": "error",
                "error": str(e),
                "metadata": {
                    "name": self.metadata.agent_name,
                    "type": self.metadata.agent_type,
                    "status": "failed",
                },
            }
