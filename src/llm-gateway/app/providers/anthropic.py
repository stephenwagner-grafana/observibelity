"""Anthropic (Claude) provider — real Phase 1 implementation.

Calls api.anthropic.com via the official `anthropic` SDK. Translates
OpenAI-style messages and tools into Anthropic's Messages API shape, parses
text + tool_use content blocks back out, and reports token usage.

Prompt caching, vision, and streaming arrive in later phases — see
docs/PROVIDERS.md.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import AsyncAnthropic

from .base import CompleteRequest, CompleteResponse, Provider

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class AnthropicProvider(Provider):
    """Claude-backed provider used by every specialist by default in Phase 1."""

    name = "anthropic"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        api_key = self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        # AsyncAnthropic tolerates a missing key at construction time; the call fails
        # later if the key is genuinely absent. That keeps unit tests happy without a key.
        self.client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic(api_key="missing")
        self.model = self.config.get("model", DEFAULT_MODEL)

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Anthropic takes the system prompt as a top-level `system=` arg, not a message."""
        system_parts: list[str] = []
        rest: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                content = m.get("content")
                if isinstance(content, str):
                    system_parts.append(content)
                elif isinstance(content, list):
                    system_parts.extend(p.get("text", "") for p in content if isinstance(p, dict))
            else:
                rest.append(m)
        system = "\n\n".join(s for s in system_parts if s) or None
        return system, rest

    @staticmethod
    def _to_anthropic_tools(tools: list[dict] | None) -> list[dict] | None:
        """Map OpenAI-style function schemas to Anthropic tool definitions."""
        if not tools:
            return None
        out: list[dict] = []
        for t in tools:
            if "function" in t:  # OpenAI shape: {type: "function", function: {...}}
                fn = t["function"]
                out.append(
                    {
                        "name": fn.get("name", "unknown"),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                    }
                )
            else:  # already in Anthropic shape
                out.append(t)
        return out

    # ------------------------------------------------------------------
    # Provider API
    # ------------------------------------------------------------------
    async def complete(self, req: CompleteRequest) -> CompleteResponse:
        model = req.model_override or self.model
        system, messages = self._split_system(req.messages)
        tools = self._to_anthropic_tools(req.tools)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": req.max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if tools is not None:
            kwargs["tools"] = tools

        response = await self.client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "input": getattr(block, "input", {}),
                    }
                )

        usage_obj = getattr(response, "usage", None)
        input_tokens = getattr(usage_obj, "input_tokens", 0) if usage_obj else 0
        output_tokens = getattr(usage_obj, "output_tokens", 0) if usage_obj else 0

        finish_reason = getattr(response, "stop_reason", "stop") or "stop"
        # Map Anthropic stop_reason vocabulary onto our canonical one.
        finish_map = {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_use"}
        finish_reason = finish_map.get(finish_reason, finish_reason)

        return CompleteResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                # cost_usd is filled in by app.main after pricing.compute_cost runs.
            },
            provider=self.name,
            model=getattr(response, "model", model),
        )

    async def healthy(self) -> bool:
        """Cheap readiness check: SDK is constructed and we have an API key."""
        return bool(getattr(self.client, "api_key", None)) and self.client.api_key != "missing"
