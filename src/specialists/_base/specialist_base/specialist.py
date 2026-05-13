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
    # Per-request LLM routing — forwarded to the gateway's /v1/complete so
    # demos (e.g. baseline.js's 80/20 Ollama vs Claude split) can pin a
    # provider/model without reconfiguring the chart. Leave unset to use
    # the gateway's configured defaults.
    provider_override: str | None = None
    model_override: str | None = None


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
        # Allow operators to override TOOL_ALLOWLIST via env var (chart sets
        # this from values.yaml > specialists[].tool_allowlist). Without the
        # override the class-level default applies — same behaviour as before.
        env_allow = os.environ.get("TOOL_ALLOWLIST", "").strip()
        if env_allow:
            parsed = [t.strip() for t in env_allow.split(",") if t.strip()]
            if parsed:
                # Replace the class-level allowlist on this instance only —
                # subclasses keep their class-level default for tests.
                self.TOOL_ALLOWLIST = parsed

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
        # Per-request overrides from the inbound app (e.g. loadgen 80/20
        # split via NeonCart /chat -> nc-chatbot -> here) trump the
        # class-level default so the demo can drive provider mix.
        if req.provider_override:
            payload["provider_override"] = req.provider_override
        if req.model_override:
            payload["model_override"] = req.model_override

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
        """Helper for subclasses: call a tool by name (must be in TOOL_ALLOWLIST).

        Propagates ``X-Caller`` (so tools with an ``ALLOWED_CALLERS`` allowlist
        recognise the specialist) and ``X-Persona-Id`` (so tools can attribute
        spans/metrics to the originating user).
        """
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
            headers = {
                "X-Caller": self.NAME,
                "X-Persona-Id": req.persona_id or "",
            }
            resp = await self.client.post(tool_url, json=args, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def _build_tool_specs(self) -> list[dict]:
        """Return tool defs the gateway/provider can translate into a real
        tool-use schema.

        Each tool is emitted in OpenAI's function-tool shape with a
        permissive ``parameters`` schema; the Anthropic provider maps that
        onto its native ``input_schema`` shape (see
        ``llm-gateway/providers/anthropic.py::_to_anthropic_tools``). Without
        a ``function`` key the gateway would receive an unknown shape and
        the LLM would never emit tool_calls — which broke every
        tool-calling specialist in Phase 1.

        Phase 2: tools self-describe via ``GET /v1/schema``; until then we
        send a permissive open object so the model can choose its own args.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t,
                    "description": f"{t} tool (see deployed schema at /v1/schema).",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    },
                },
            }
            for t in self.TOOL_ALLOWLIST
        ]
