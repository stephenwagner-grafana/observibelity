"""Ollama provider — Phase 1 stub-but-functional.

POSTs to {OLLAMA_BASE_URL}/api/chat using the native Ollama chat API. Token
counts come back as `prompt_eval_count` / `eval_count`. Tool-calling is
supported by recent Ollama builds but we keep the surface simple in Phase 1.

Lockstep model rotation
-----------------------
The original ObserVIBElity design calls for the entire fleet of Ollama-bound
specialists to point at the SAME model for a given 5-minute window, then all
flip to the next model in the rotation pool simultaneously. That mimics how
real LLM teams A/B-test models hour-over-hour and gives the Model Winner
dashboard a meaningful per-model slice to compare.

The trick that makes it "lockstep" without any shared state is
``int(time.time()) // window_seconds``: every pod running this provider gets
the SAME bucket value at the SAME wall-clock instant, so they all pick the
same index into ``rotation_models`` simultaneously. No leader-election, no
ConfigMap reloader, no rotation controller — just wall clocks agreeing.

Per-request overrides (``CompleteRequest.model_override`` set by baseline.js
or a specialist explicitly pinning a model for A/B tests) still win — only
the *default* model selection is rotated.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from opentelemetry import trace

from .base import CompleteRequest, CompleteResponse, Provider

log = logging.getLogger(__name__)
tracer = trace.get_tracer("llm_gateway.ollama")

DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0
DEFAULT_ROTATION_WINDOW_SECONDS = 300  # 5 minutes


def _parse_rotation_models(raw: str | None) -> list[str]:
    """Split a comma-separated env-var into clean model names."""
    if not raw:
        return []
    return [m.strip() for m in raw.split(",") if m.strip()]


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
        # Single-model fallback when rotation is disabled or no rotation pool
        # is configured. Kept as ``self.model`` for compat with code paths
        # (and tests) that read it directly via ``getattr(provider, "model")``.
        self.model = self.config.get("model", DEFAULT_MODEL)
        self.timeout = float(self.config.get("timeout", DEFAULT_TIMEOUT))

        # --- Lockstep rotation config (env-driven; chart wires these in) ---
        self.rotation_enabled = (
            os.environ.get("OLLAMA_ROTATION_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        try:
            self.rotation_window = int(
                os.environ.get(
                    "OLLAMA_ROTATION_WINDOW_SECONDS",
                    str(DEFAULT_ROTATION_WINDOW_SECONDS),
                )
            )
        except ValueError:
            self.rotation_window = DEFAULT_ROTATION_WINDOW_SECONDS
        if self.rotation_window <= 0:
            self.rotation_window = DEFAULT_ROTATION_WINDOW_SECONDS
        self.rotation_models = _parse_rotation_models(
            os.environ.get("OLLAMA_ROTATION_MODELS")
        ) or [self.model]
        if self.rotation_enabled:
            log.info(
                "Ollama lockstep rotation: window=%ss models=%s",
                self.rotation_window,
                self.rotation_models,
            )

    def _current_rotation_model(self) -> tuple[str, int]:
        """Return (model_name, bucket_id) for the current wall-clock window.

        Bucket id is ``floor(epoch_seconds / window)`` — identical across every
        pod that calls this at the same instant, which is what makes the
        rotation cluster-wide *lockstep* without any coordination.
        """
        if not self.rotation_enabled or not self.rotation_models:
            return self.model, 0
        bucket = int(time.time()) // self.rotation_window
        model = self.rotation_models[bucket % len(self.rotation_models)]
        return model, bucket

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
        # Per-request model_override (loadgen baseline.js / specialist A/B test)
        # always wins; otherwise the lockstep rotation picks the current model.
        rotation_model, rotation_bucket = self._current_rotation_model()
        model = req.model_override or rotation_model

        # Surface the rotation state on the active span so dashboards can
        # show *which* model the rotation pointed at for each call, and so
        # Tempo searches like `ollama.rotation.bucket=12345` can pull the
        # exact set of requests that landed in one rotation window.
        try:
            current_span = trace.get_current_span()
            if current_span is not None:
                if self.rotation_enabled and not req.model_override:
                    current_span.set_attribute("ollama.rotation.enabled", True)
                    current_span.set_attribute("ollama.rotation.bucket", rotation_bucket)
                    current_span.set_attribute(
                        "ollama.rotation.window_seconds", self.rotation_window
                    )
                    current_span.set_attribute("ollama.rotation.model", rotation_model)
                    current_span.set_attribute(
                        "ollama.rotation.pool_size", len(self.rotation_models)
                    )
                else:
                    current_span.set_attribute("ollama.rotation.enabled", False)
        except Exception:  # noqa: BLE001 — telemetry must never break a request
            pass

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
