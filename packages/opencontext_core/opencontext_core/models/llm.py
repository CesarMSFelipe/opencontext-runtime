"""LLM gateway request and response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.models.context import ContextItem


class LLMRequest(BaseModel):
    """Provider-neutral request passed to an LLM gateway."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(description="Final assembled prompt.")
    system_prompt: str = Field(
        default="",
        description="Optional system prompt (e.g. the active persona) sent as a system message.",
    )
    provider: str = Field(description="Configured provider key.")
    model: str = Field(description="Configured model name.")
    max_output_tokens: int = Field(gt=0, description="Maximum output tokens requested.")
    context_items: list[ContextItem] = Field(
        default_factory=list,
        description="Context items included in the prompt.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Gateway-specific or trace metadata.",
    )


class LLMResponse(BaseModel):
    """Provider-neutral response returned by an LLM gateway."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Generated answer text.")
    provider: str = Field(description="Provider that produced the response.")
    model: str = Field(description="Model that produced the response.")
    input_tokens: int = Field(ge=0, description="Estimated or reported input tokens.")
    output_tokens: int = Field(ge=0, description="Estimated or reported output tokens.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Gateway-specific response metadata.",
    )
