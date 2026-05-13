"""Ollama provider — Phase 1 stub-but-functional.

POSTs to {OLLAMA_BASE_URL}/api/chat using the native Ollama chat API. Token
counts come back as `prompt_eval_count` / `eval_count`. Tool-calling is
supported by recent Ollama builds but we keep the surface simple in Phase 1.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import CompleteRequest, CompleteResponse, Provider

log = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0


class OllamaProvider(Provider):
    """Ollama-backed provider for users running a local model."""

    name = "ollama"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.base_url = (
            self.config.get("base_url")
            or os.environ.get("OLLAMA_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = self.config.get("model", DEFAULT_MODEL)
        self.timeout = float(self.config.get("timeout", DEFAULT_TIMEOUT))

    @staticmethod
    def _flatten_messages(messages: list[dict]) -> list[dict]:
        """Coerce OpenAI-style messages to Ollama's flat {role, content:str} shape.

        OpenAI permits content as a list of typed parts (``[{"type": "text", "text": ...}]``)
        or a list of tool-result blocks; Ollama's chat API wants ``content`` as a single
        string. We flatten any list to plain text so tool-result echoes from the
        specialist base don't trip Ollama with a 400.
        """
        out: list[dict] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                parts: list[str] = []
                for c in content:
                    if isinstance(c, dict):
                        # Common shapes: {"type": "text", "text": "..."} or
                        # {"type": "tool_result", "content": "..."}
                        parts.append(str(c.get("text") or c.get("content") or ""))
                    else:
                        parts.append(str(c))
                content = "\n".join(p for p in parts if p)
            out.append({"role": role, "content": str(content)})
        return out

    async def complete(self, req: CompleteRequest) -> CompleteResponse:
        model = req.model_override or self.model
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._flatten_messages(req.messages),
            "stream": False,
            "options": {"num_predict": req.max_tokens, "temperature": 0.7},
        }
        if req.tools:
            payload["tools"] = req.tools

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        message = data.get("message", {}) or {}
        content = message.get("content", "") or ""
        raw_tool_calls = message.get("tool_calls", []) or []
        tool_calls = [
            {
                "id": tc.get("id", ""),
                "name": (tc.get("function") or {}).get("name", "") or tc.get("name", ""),
                "input": (tc.get("function") or {}).get("arguments")
                or tc.get("arguments")
                or {},
            }
            for tc in raw_tool_calls
        ]

        finish_reason = "tool_use" if tool_calls else ("length" if data.get("done_reason") == "length" else "stop")

        return CompleteResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage={
                "input_tokens": int(data.get("prompt_eval_count", 0)),
                "output_tokens": int(data.get("eval_count", 0)),
            },
            provider=self.name,
            model=data.get("model", model),
        )

    async def healthy(self) -> bool:
        """GET / on the Ollama base URL — fast, no model required."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(self.base_url + "/")
                return r.status_code < 500
        except Exception:  # noqa: BLE001 — readiness probe must never raise.
            return False
