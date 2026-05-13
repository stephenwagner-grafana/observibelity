"""Provider base class + shared Pydantic models.

The same Provider abstraction shape is mirrored in
`tools/deploy_doctor/providers/base.py` — keep them aligned. The llm-gateway
contract is richer (messages + tools + usage) than the deploy-doctor one
(single-shot diagnose call), so we redefine here rather than inherit.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class CompleteRequest(BaseModel):
    """Inbound request from a specialist to /v1/complete."""

    specialist: str = Field(..., description="Specialist app name, e.g. nc-chatbot.")
    messages: list[dict] = Field(
        ..., description="OpenAI-style messages: [{role, content}, ...]."
    )
    tools: list[dict] | None = Field(
        default=None, description="OpenAI-style tool definitions (function schemas)."
    )
    model_override: str | None = Field(
        default=None,
        description="If set, the gateway routes to this exact model regardless of provider default.",
    )
    provider_override: str | None = Field(
        default=None,
        description="If set, the gateway routes to this provider (e.g. 'anthropic', 'ollama') instead of the default.",
    )
    max_tokens: int = Field(default=2000, ge=1, le=200_000)
    ai_o11y: dict = Field(
        default_factory=dict,
        description="Demo-level metadata: {usecase, persona_id, traffic_origin}.",
    )


class CompleteResponse(BaseModel):
    """Outbound response from /v1/complete."""

    content: str = Field(..., description="Concatenated text content from the model.")
    tool_calls: list[dict] = Field(
        default_factory=list,
        description="Tool calls the model asked the specialist to run. Empty if none.",
    )
    finish_reason: str = Field(
        default="stop",
        description="Why the model stopped: stop | tool_use | length | error.",
    )
    usage: dict = Field(
        default_factory=dict,
        description="{input_tokens, output_tokens, cost_usd: {input_usd, output_usd, total_usd}}.",
    )
    provider: str = Field(..., description="Provider name that handled the call.")
    model: str = Field(..., description="Concrete model id used.")


class Provider(ABC):
    """Base class for LLM providers used by the gateway."""

    name: str = "base"

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    async def complete(self, req: CompleteRequest) -> CompleteResponse:
        """Execute the completion. Subclasses implement provider-specific logic."""
        ...

    async def healthy(self) -> bool:
        """Lightweight readiness check. Subclasses override with a real probe."""
        return True
