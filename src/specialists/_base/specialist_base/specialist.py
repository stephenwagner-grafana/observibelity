"""Shared Specialist base class.

Specialists are sub-agent pods. Each one:
  1. Receives a request from an app (or another specialist)
  2. Calls the llm-gateway with a tool allowlist
  3. Optionally calls tools (via k8s service names)
  4. Returns a structured response

Subclasses set NAME / TOOL_ALLOWLIST / SYSTEM_PROMPT and implement ``handle``.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx
from opentelemetry import trace
from pydantic import BaseModel, Field

tracer = trace.get_tracer(__name__)


class SpecialistRequest(BaseModel):
    """Inbound request to a specialist's POST /v1/run endpoint."""

    message: str
    persona_id: str | None = None
    session_id: str | None = None
    usecase: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class SpecialistResponse(BaseModel):
    """Outbound response from a specialist."""

    reply: str
    tool_calls: list[dict] = Field(default_factory=list)
    cost_usd: float = 0.0
    span_id: str | None = None


class Specialist(ABC):
    """Abstract base for all specialist pods."""

    NAME: str = "unknown-specialist"
    TOOL_ALLOWLIST: list[str] = []
    SYSTEM_PROMPT: str = "You are a helpful specialist."
    DEFAULT_MODEL: str | None = None

    def __init__(self) -> None:
        self.llm_gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm-gateway")
        self.client = httpx.AsyncClient(timeout=30.0)

    @abstractmethod
    async def handle(self, req: SpecialistRequest) -> SpecialistResponse:
        """Subclasses implement the per-specialist workflow here."""
        ...

    async def call_gateway(
        self,
        messages: list[dict],
        req: SpecialistRequest,
        max_tokens: int = 1500,
    ) -> dict:
        """Helper for subclasses: call llm-gateway with the specialist's tool allowlist."""
        payload: dict[str, Any] = {
            "specialist": self.NAME,
            "messages": messages,
            "tools": self._build_tool_specs(),
            "max_tokens": max_tokens,
            "ai_o11y": {
                "usecase": req.usecase,
                "persona_id": req.persona_id,
                "traffic_origin": "continuous" if req.usecase else "interactive",
            },
        }
        if self.DEFAULT_MODEL:
            payload["model_override"] = self.DEFAULT_MODEL

        with tracer.start_as_current_span(f"specialist.{self.NAME}.call_gateway") as span:
            span.set_attribute("ai_o11y.specialist", self.NAME)
            if req.usecase:
                span.set_attribute("ai_o11y.usecase", req.usecase)
            if req.persona_id:
                # Mirror the gateway's persona attr on the specialist span so
                # Tempo/Loki filters work even before the gateway call returns.
                span.set_attribute("ai_o11y.persona_id", req.persona_id)
            resp = await self.client.post(
                f"{self.llm_gateway_url}/v1/complete",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def call_tool(
        self,
        tool_name: str,
        args: dict,
        req: SpecialistRequest,
    ) -> dict:
        """Helper for subclasses: call a tool by name (must be in TOOL_ALLOWLIST)."""
        if tool_name not in self.TOOL_ALLOWLIST:
            raise PermissionError(
                f"{self.NAME} not allowed to call {tool_name}"
            )
        # k8s service name: underscores -> dashes
        tool_url = f"http://{tool_name.replace('_', '-')}/v1/invoke"
        with tracer.start_as_current_span(f"tool.{tool_name}") as span:
            span.set_attribute("ai_o11y.tool", tool_name)
            span.set_attribute("ai_o11y.specialist", self.NAME)
            if req.persona_id:
                span.set_attribute("ai_o11y.persona_id", req.persona_id)
            if req.usecase:
                span.set_attribute("ai_o11y.usecase", req.usecase)
            resp = await self.client.post(tool_url, json=args)
            resp.raise_for_status()
            return resp.json()

    def _build_tool_specs(self) -> list[dict]:
        # Phase 1: hardcoded. In Phase 2, tools self-describe via /v1/schema.
        return [{"name": t, "type": "function"} for t in self.TOOL_ALLOWLIST]
