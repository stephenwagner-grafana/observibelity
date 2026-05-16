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

import json as _json
import logging
import os
import random as _random
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
DEFAULT_KEEP_ALIVE = "30m"  # match prewarm task + daemon-side OLLAMA_KEEP_ALIVE
_NO_TOOLS_MARKER = "does not support tools"
# Saturation threshold: when this many requests are in-flight on a single
# gateway pod, the dispatcher treats Ollama as "at capacity" and routes
# overflow to Claude (subject to daily budget). Defaults to NUM_PARALLEL=8
# on the .240 daemon so we spill the moment Ollama starts queueing.
OLLAMA_SATURATION_THRESHOLD = int(
    os.environ.get("OLLAMA_SATURATION_THRESHOLD", "8")
)


class _NoToolsError(Exception):
    """Internal signal: Ollama 400'd with the "does not support tools" marker.

    Caught inside the provider to drive a one-shot retry with the tools field
    stripped from the payload. Never propagates out of the provider.
    """


def shuffle_models_by_hour(models: list[str], hour_bucket: int) -> list[str]:
    """Return the rotation models deterministically shuffled per hour.

    Every pod that calls this with the same hour_bucket produces the same
    order — lockstep within the hour. At each UTC hour boundary the seed
    changes and the rotation order is freshly randomized; all pods flip
    to the new order simultaneously because hour_bucket increments at the
    same wall-clock instant everywhere.
    """
    shuffled = list(models)
    _random.Random(hour_bucket).shuffle(shuffled)
    return shuffled


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
        # Tells the Ollama daemon how long to keep this model resident
        # after the request returns. The prewarm task uses the same value
        # so the active model and its pre-loaded successor share lifetimes.
        self.keep_alive = self.config.get("keep_alive") or os.environ.get(
            "OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE
        )

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
        # In-flight request counter — single-threaded asyncio = race-free
        # without a lock as long as increments don't span an await. The
        # dispatcher reads this to decide spillover-to-Claude.
        self._in_flight: int = 0
        if self.rotation_enabled:
            log.info(
                "Ollama lockstep rotation: window=%ss models=%s",
                self.rotation_window,
                self.rotation_models,
            )

    @property
    def in_flight(self) -> int:
        """Currently-executing Ollama requests on this gateway pod."""
        return self._in_flight

    @property
    def is_saturated(self) -> bool:
        """True when in-flight count is at/above the saturation threshold."""
        return self._in_flight >= OLLAMA_SATURATION_THRESHOLD

    def _current_rotation_model(self) -> tuple[str, int]:
        """Return (model_name, bucket_id) for the current wall-clock window.

        Bucket id is ``floor(epoch_seconds / window)`` — identical across every
        pod that calls this at the same instant, which is what makes the
        rotation cluster-wide *lockstep* without any coordination.

        Within each UTC hour the rotation order is a deterministic shuffle
        of ``rotation_models`` seeded by the hour bucket (see
        ``shuffle_models_by_hour``). At the hour boundary all pods reshuffle
        simultaneously and the new order takes effect.
        """
        if not self.rotation_enabled or not self.rotation_models:
            return self.model, 0
        now = int(time.time())
        bucket = now // self.rotation_window
        hour_bucket = now // 3600
        position = (now % 3600) // self.rotation_window
        shuffled = shuffle_models_by_hour(self.rotation_models, hour_bucket)
        model = shuffled[position % len(shuffled)]
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
            "keep_alive": self.keep_alive,
            "options": {"num_predict": req.max_tokens, "temperature": 0.7},
        }
        if req.tools:
            payload["tools"] = req.tools

        self._in_flight += 1
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    r = await client.post(f"{self.base_url}/api/chat", json=payload)
                    r.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    # If Ollama 400s because the active rotation model doesn't
                    # support tool-calling, strip the tools field and retry once.
                    # The specialist gets a no-tool answer instead of an error;
                    # the demo stays alive across the no-tool half of the pool.
                    if not (
                        exc.response.status_code == 400
                        and "tools" in payload
                        and _NO_TOOLS_MARKER in (exc.response.text or "")
                    ):
                        raise
                    log.info(
                        "ollama 400 (no-tools): retrying without tools, model=%s",
                        payload.get("model"),
                    )
                    payload_no_tools = {k: v for k, v in payload.items() if k != "tools"}
                    r = await client.post(f"{self.base_url}/api/chat", json=payload_no_tools)
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
        finally:
            self._in_flight = max(0, self._in_flight - 1)

    # ------------------------------------------------------------------
    # Phase A: gateway-internal streaming (nc-chatbot only)
    # ------------------------------------------------------------------
    async def complete_stream(
        self, req: CompleteRequest
    ) -> tuple[CompleteResponse, float | None]:
        """Stream /api/chat and assemble the same CompleteResponse.

        Ollama emits newline-delimited JSON when ``stream: true``. Each
        chunk has ``message.content`` (a piece of the assistant reply); the
        final chunk has ``done: true`` plus ``prompt_eval_count`` /
        ``eval_count`` which we use for token usage. We must read until the
        ``done`` chunk — stopping early loses token counts.
        """
        rotation_model, rotation_bucket = self._current_rotation_model()
        model = req.model_override or rotation_model

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
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": req.max_tokens, "temperature": 0.7},
        }
        if req.tools:
            payload["tools"] = req.tools

        async def _consume(client, send_payload):
            """Stream /api/chat with send_payload; return result state.

            Returns a 7-tuple (text_parts, tool_calls_raw, prompt_eval_count,
            eval_count, done_reason, last_model, ttft_ms) — or raises
            ``_NoToolsError`` if Ollama 400s with the "does not support tools"
            marker, signalling the caller to retry without tools.
            """
            text_parts: list[str] = []
            tool_calls_raw: list[dict] = []
            prompt_eval_count = 0
            eval_count = 0
            done_reason: str | None = None
            last_model_local = send_payload.get("model")
            start = time.monotonic()
            ttft_ms: float | None = None
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=send_payload
            ) as r:
                if r.status_code == 400 and "tools" in send_payload:
                    body = (await r.aread()).decode("utf-8", errors="replace")
                    if _NO_TOOLS_MARKER in body:
                        raise _NoToolsError()
                    # Other 400 — re-raise via raise_for_status with the body
                    # already drained, otherwise httpx would try to read it.
                    r.raise_for_status()
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    msg = chunk.get("message") or {}
                    piece = msg.get("content") or ""
                    if piece:
                        if ttft_ms is None:
                            ttft_ms = (time.monotonic() - start) * 1000.0
                        text_parts.append(piece)
                    tc = msg.get("tool_calls") or []
                    if tc:
                        tool_calls_raw.extend(tc)
                    if chunk.get("model"):
                        last_model_local = chunk["model"]
                    if chunk.get("done"):
                        prompt_eval_count = int(chunk.get("prompt_eval_count", 0) or 0)
                        eval_count = int(chunk.get("eval_count", 0) or 0)
                        done_reason = chunk.get("done_reason")
                        final_msg = chunk.get("message") or {}
                        final_tc = final_msg.get("tool_calls") or []
                        if final_tc and not tool_calls_raw:
                            tool_calls_raw.extend(final_tc)
                        break
            return (
                text_parts, tool_calls_raw, prompt_eval_count, eval_count,
                done_reason, last_model_local, ttft_ms,
            )

        self._in_flight += 1
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    (text_parts, tool_calls_raw, prompt_eval_count, eval_count,
                     done_reason, last_model, ttft_ms) = await _consume(client, payload)
                except _NoToolsError:
                    log.info(
                        "ollama 400 (no-tools, streaming): retrying without tools, model=%s",
                        payload.get("model"),
                    )
                    payload_no_tools = {k: v for k, v in payload.items() if k != "tools"}
                    (text_parts, tool_calls_raw, prompt_eval_count, eval_count,
                     done_reason, last_model, ttft_ms) = await _consume(client, payload_no_tools)
        finally:
            self._in_flight = max(0, self._in_flight - 1)

        tool_calls = [
            {
                "id": tc.get("id", ""),
                "name": (tc.get("function") or {}).get("name", "") or tc.get("name", ""),
                "input": (tc.get("function") or {}).get("arguments")
                or tc.get("arguments")
                or {},
            }
            for tc in tool_calls_raw
        ]
        finish_reason = (
            "tool_use" if tool_calls else ("length" if done_reason == "length" else "stop")
        )

        resp = CompleteResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage={
                "input_tokens": prompt_eval_count,
                "output_tokens": eval_count,
            },
            provider=self.name,
            model=last_model,
        )
        return resp, ttft_ms

    async def healthy(self) -> bool:
        """GET / on the Ollama base URL — fast, no model required."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(self.base_url + "/")
                return r.status_code < 500
        except Exception:  # noqa: BLE001 — readiness probe must never raise.
            return False
