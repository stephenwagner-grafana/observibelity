"""Ollama prewarm task — keeps exactly two models hot at any time.

Background asyncio task that mirrors the lockstep rotation in
``providers/ollama.py`` and ensures the Ollama daemon has exactly the
currently-active rotation model AND the next-rotation model loaded in
VRAM at all times.

How it works
------------
On every bucket flip (i.e. when ``int(time.time()) // window`` increments)
the task fires two fire-and-forget calls directly against Ollama's
``/api/generate`` endpoint:

1. Pre-warm the *next* model with ``keep_alive=<OLLAMA_KEEP_ALIVE>`` and a
   1-token prompt so it loads into VRAM before traffic ever hits it.
2. Evict the *previous* model with ``keep_alive=0`` so the daemon unloads
   it and frees VRAM for the next pre-warm — strictly two models warm.

Both calls bypass ``/v1/complete`` entirely, so they don't add to the
gateway's metrics, traces, or cost counters.

Safety
------
- Pre-warm + evict run as ``asyncio.create_task``; they never block live
  requests.
- HTTP errors are logged and dropped; no retries, no error storms.
- Idempotent: re-loading an already-warm model is a no-op for Ollama;
  evicting an already-unloaded model is also a no-op.
- Capped by Ollama's ``OLLAMA_MAX_LOADED_MODELS`` on the daemon side, so
  even a buggy ticker can't OOM the GPU.

Multi-replica note
------------------
Every llm-gateway replica runs its own copy of this task. With N replicas
you'll see N pre-warm/evict calls per flip — wasteful but not harmful
(loads are idempotent). Add jitter + a coordinator if N gets large.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

log = logging.getLogger("llm_gateway.prewarm")


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [m.strip() for m in raw.split(",") if m.strip()]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


class PrewarmTask:
    """Background ticker that keeps active + next rotation models warm.

    The task is purely time-driven: every ``tick_interval`` seconds it
    computes the current rotation bucket; if the bucket has changed since
    the last tick, it dispatches one pre-warm and one evict call. No
    shared state with the OllamaProvider — both consult the same env
    vars and the same wall clock, which is exactly what makes the
    rotation lockstep without coordination.
    """

    def __init__(
        self,
        *,
        base_url: str,
        models: list[str],
        window_seconds: int,
        keep_alive: str = "30m",
        tick_interval_seconds: int = 5,
        http_timeout_seconds: float = 10.0,
    ) -> None:
        if not models:
            raise ValueError("PrewarmTask requires at least one rotation model")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.models = list(models)
        self.window = window_seconds
        self.keep_alive = keep_alive
        self.tick_interval = max(1, min(tick_interval_seconds, window_seconds // 2 or 1))
        self.http_timeout = http_timeout_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_handled_bucket: int | None = None

    # -- pure helpers (testable without I/O) ----------------------------
    def current_bucket(self, ts: float | None = None) -> int:
        ts = time.time() if ts is None else ts
        return int(ts) // self.window

    def model_at(self, bucket: int) -> str:
        return self.models[bucket % len(self.models)]

    # -- I/O ------------------------------------------------------------
    async def _send(self, model: str, *, keep_alive: str | int) -> None:
        """Direct ``/api/generate`` call. Empty prompt + keep_alive=0 unloads."""
        payload: dict = {"model": model, "keep_alive": keep_alive, "stream": False}
        if keep_alive != 0:
            # Tiny generation so Ollama actually loads weights into VRAM.
            payload["prompt"] = "hi"
            payload["options"] = {"num_predict": 1}
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                r = await client.post(f"{self.base_url}/api/generate", json=payload)
                if r.status_code >= 400:
                    log.warning(
                        "prewarm send failed: model=%s keep_alive=%s status=%s body=%s",
                        model, keep_alive, r.status_code, r.text[:200],
                    )
                else:
                    action = "evict" if keep_alive == 0 else "prewarm"
                    log.info("prewarm %s ok: model=%s", action, model)
        except Exception as exc:  # noqa: BLE001 — observability must not crash
            log.warning("prewarm send error: model=%s keep_alive=%s err=%s",
                        model, keep_alive, exc)

    # -- ticker ---------------------------------------------------------
    async def _handle_flip(self, bucket: int, *, evict_previous: bool = True) -> None:
        """Dispatch pre-warm(next) + evict(previous) for a freshly-flipped bucket.

        ``evict_previous`` is False on the very first tick after startup
        because we don't know whether the previous model is actually
        resident in VRAM — issuing keep_alive=0 against an unloaded model
        would force Ollama to load-then-unload it (the exact 1-4s spike
        we're trying to avoid). After we've observed at least one real
        rotation flip in-process, the previous model WAS active in the
        window before, so eviction is correct.
        """
        current = self.model_at(bucket)
        next_model = self.model_at(bucket + 1)
        prev_model = self.model_at(bucket - 1)

        # Pre-warm the upcoming model so the next flip is seamless.
        # Skip if it's the same as the current (pool of 1) — already warm.
        if next_model != current:
            log.info(
                "prewarm flip: bucket=%d current=%s next=%s prev=%s evict=%s",
                bucket, current, next_model, prev_model, evict_previous,
            )
            asyncio.create_task(self._send(next_model, keep_alive=self.keep_alive))

        # Evict the previous model so we stay at <= 2 warm models.
        # Skip if it collides with current or next (pool size 1 or 2)
        # or if this is the first tick (model may not be loaded).
        if evict_previous and prev_model != current and prev_model != next_model:
            asyncio.create_task(self._send(prev_model, keep_alive=0))

    async def _tick(self) -> None:
        bucket = self.current_bucket()
        if self._last_handled_bucket == bucket:
            return
        is_first_tick = self._last_handled_bucket is None
        try:
            await self._handle_flip(bucket, evict_previous=not is_first_tick)
        finally:
            self._last_handled_bucket = bucket

    async def _run(self) -> None:
        log.info(
            "prewarm task started: base_url=%s models=%d window=%ds keep_alive=%s tick=%ds",
            self.base_url, len(self.models), self.window,
            self.keep_alive, self.tick_interval,
        )
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 — never let this kill the gateway
                log.exception("prewarm tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_interval)
            except asyncio.TimeoutError:
                pass
        log.info("prewarm task stopped")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()


def maybe_start_prewarm() -> PrewarmTask | None:
    """Read env + start a PrewarmTask, or return None if disabled / not applicable."""
    if not _env_bool("OLLAMA_PREWARM_ENABLED", True):
        log.info("OLLAMA_PREWARM_ENABLED=false; prewarm task disabled")
        return None
    if not _env_bool("OLLAMA_ROTATION_ENABLED", True):
        log.info("OLLAMA_ROTATION_ENABLED=false; nothing to prewarm")
        return None
    models = _parse_csv(os.environ.get("OLLAMA_ROTATION_MODELS"))
    if len(models) < 2:
        log.info("OLLAMA_ROTATION_MODELS has <2 entries; prewarm task disabled")
        return None
    base_url = (
        os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
    ).rstrip("/")
    window = _env_int("OLLAMA_ROTATION_WINDOW_SECONDS", 300)
    if window <= 0:
        window = 300
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
    tick_interval = _env_int("OLLAMA_PREWARM_TICK_SECONDS", 5)

    task = PrewarmTask(
        base_url=base_url,
        models=models,
        window_seconds=window,
        keep_alive=keep_alive,
        tick_interval_seconds=tick_interval,
    )
    task.start()
    return task
