"""Anthropic (Claude) provider — real Phase 1 implementation.

Calls api.anthropic.com via the official `anthropic` SDK. Translates
OpenAI-style messages and tools into Anthropic's Messages API shape, parses
text + tool_use content blocks back out, and reports token usage.

Prompt caching + vision arrive in later phases — see docs/PROVIDERS.md.
Phase A streaming (gateway-internal, nc-chatbot only) is implemented in
:meth:`AnthropicProvider.complete_stream` — the public ``complete()``
contract stays non-streaming so other specialists are untouched.
"""
from __future__ import annotations

import logging
import os
import time
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
        # Honor the Helm chart's env var (ANTHROPIC_DEFAULT_MODEL) as well as the
        # legacy ANTHROPIC_MODEL so operators picking a model via values.yaml are
        # respected. Explicit config["model"] always wins.
        self.model = (
            self.config.get("model")
            or os.environ.get("ANTHROPIC_DEFAULT_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or DEFAULT_MODEL
        )

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_anthropic_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Translate OpenAI-style messages -> (system prompt, Anthropic messages).

        The specialist base sends us OpenAI-shaped messages because it's the
        more permissive of the two formats. Anthropic's Messages API needs:

        * System messages collapsed onto a top-level ``system=`` argument.
        * Assistant messages that triggered tool calls expanded into content
          blocks of ``{type: text}`` and/or ``{type: tool_use}``.
        * Tool result messages re-emitted as a *user* message containing a
          ``{type: tool_result, tool_use_id, content}`` block. Anthropic
          rejects ``role: "tool"`` outright (400 from the public API).

        Without this conversion the second round-trip in a tool-using
        specialist (e.g. nc-chatbot answering "do you have mice?") 400s with
        ``Unexpected role 'tool'``.
        """
        system_parts: list[str] = []
        anth_messages: list[dict] = []

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                content = msg.get("content")
                if isinstance(content, str):
                    system_parts.append(content)
                elif isinstance(content, list):
                    system_parts.extend(
                        p.get("text", "") for p in content if isinstance(p, dict)
                    )
                continue

            if role == "tool":
                # Tool result -> user message with a tool_result content block.
                anth_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": (
                                    msg.get("tool_call_id")
                                    or msg.get("id")
                                    or "toolu_unknown"
                                ),
                                "content": str(msg.get("content", "")),
                            }
                        ],
                    }
                )
                continue

            if role == "assistant" and msg.get("tool_calls"):
                # Assistant turn that emitted tool_use(s) — expand to content blocks.
                blocks: list[dict] = []
                if msg.get("content"):
                    blocks.append({"type": "text", "text": str(msg["content"])})
                for tc in msg["tool_calls"]:
                    fn = tc.get("function") or {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id") or "toolu_unknown",
                            "name": tc.get("name") or fn.get("name") or "unknown",
                            "input": (
                                tc.get("input")
                                or tc.get("args")
                                or fn.get("arguments")
                                or {}
                            ),
                        }
                    )
                anth_messages.append({"role": "assistant", "content": blocks})
                continue

            # Plain user / assistant message — pass through unchanged.
            anth_messages.append(
                {"role": role, "content": msg.get("content", "")}
            )

        system = "\n\n".join(s for s in system_parts if s) or None
        return system, anth_messages

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
        system, messages = self._to_anthropic_messages(req.messages)
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

    # ------------------------------------------------------------------
    # Phase A: gateway-internal streaming (nc-chatbot only)
    # ------------------------------------------------------------------
    async def complete_stream(
        self, req: CompleteRequest
    ) -> tuple[CompleteResponse, float | None]:
        """Stream the Messages API and assemble the same CompleteResponse.

        Uses ``client.messages.stream()`` which exposes:

        * per-chunk text deltas (used to capture wall-clock TTFT)
        * ``.get_final_message()`` after the stream closes — carries the
          fully populated ``usage`` block, including the count that only
          shows up in the ``message_delta`` event.

        Returns ``(CompleteResponse, ttft_ms_or_None)``. ``ttft_ms`` is
        ``None`` when no non-empty text chunk was observed (tool-only
        responses, errors before first delta, etc.).
        """
        model = req.model_override or self.model
        system, messages = self._to_anthropic_messages(req.messages)
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

        start = time.monotonic()
        ttft_ms: float | None = None

        async with self.client.messages.stream(**kwargs) as stream:
            # text_stream yields the text deltas as they arrive. First
            # non-empty chunk = TTFT. We don't accumulate text here — the
            # final message has it in canonical block form, which is what
            # the non-streaming path returns.
            async for chunk in stream.text_stream:
                if chunk and ttft_ms is None:
                    ttft_ms = (time.monotonic() - start) * 1000.0
            # Drain anything left (tool_use blocks etc. — text_stream only
            # yields text). get_final_message() blocks until the stream is
            # fully consumed and the message_delta carrying usage arrived.
            final = await stream.get_final_message()

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in final.content:
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

        usage_obj = getattr(final, "usage", None)
        input_tokens = getattr(usage_obj, "input_tokens", 0) if usage_obj else 0
        output_tokens = getattr(usage_obj, "output_tokens", 0) if usage_obj else 0

        finish_reason = getattr(final, "stop_reason", "stop") or "stop"
        finish_map = {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_use"}
        finish_reason = finish_map.get(finish_reason, finish_reason)

        resp = CompleteResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            provider=self.name,
            model=getattr(final, "model", model),
        )
        return resp, ttft_ms

    async def healthy(self) -> bool:
        """Cheap readiness check: SDK is constructed and we have an API key."""
        return bool(getattr(self.client, "api_key", None)) and self.client.api_key != "missing"
