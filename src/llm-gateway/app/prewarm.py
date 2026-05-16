"""Retired Ollama prewarm task — stub kept for backwards-compatible imports.

The fixed-window rotation that this module used to drive has been replaced
by the dynamic model-pool scheduler in ``app.scheduler``. New code should
use ``maybe_start_scheduler`` instead of ``maybe_start_prewarm``.

The classes + factory below are no-op stand-ins so any external caller
that still imports them (tests, vendored copies, downstream tools) keeps
parsing. ``maybe_start_prewarm`` always returns ``None``.

Removed behavior:
  * Bucket math (``current_bucket`` / ``model_at``) — the scheduler is
    not time-windowed.
  * /api/generate pre-warm + evict POSTs — the scheduler issues its own
    warm-up call when it moves a model out of the queue.

Pre-existing tests under ``tests/test_prewarm.py`` test specific behaviors
that no longer exist; they should be removed in the same commit that
ships the scheduler, but leaving the file in pytest's collection while
this module is a stub keeps the deletion auditable.
"""
from __future__ import annotations

import logging

log = logging.getLogger("llm_gateway.prewarm")


class PrewarmTask:
    """No-op stub. The model-pool scheduler subsumed this class."""

    def __init__(self, *args, **kwargs) -> None:
        # Preserve the legacy constructor signature so anything that
        # builds one directly doesn't TypeError. State is intentionally
        # left blank — call sites won't observe anything useful.
        self.base_url = ""
        self.models: list[str] = []
        self.window = 0
        self.keep_alive = ""

    def current_bucket(self, ts: float | None = None) -> int:
        return 0

    def model_at(self, bucket: int) -> str:
        return ""

    async def _send(self, model: str, *, keep_alive: str | int) -> None:
        return None

    async def _handle_flip(self, bucket: int, *, evict_previous: bool = True) -> None:
        return None

    async def _tick(self) -> None:
        return None

    def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def maybe_start_prewarm() -> PrewarmTask | None:
    """Always returns ``None`` — superseded by ``app.scheduler``."""
    log.debug("prewarm retired; using app.scheduler instead")
    return None


__all__ = ["PrewarmTask", "maybe_start_prewarm"]
