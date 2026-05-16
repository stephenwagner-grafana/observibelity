"""Tests for the Ollama prewarm task.

The prewarm task has two halves:

* Pure math — bucket index + model lookup. Deterministic, exercised with
  ``time.time`` patches.
* I/O — POSTs to ``/api/generate``. Exercised with an injected fake
  ``_send`` so we don't need an Ollama daemon.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

from app.prewarm import PrewarmTask, maybe_start_prewarm


def _make_task(**overrides) -> PrewarmTask:
    kwargs = dict(
        base_url="http://stub:11434",
        models=["m0", "m1", "m2", "m3"],
        window_seconds=300,
        keep_alive="30m",
        tick_interval_seconds=1,
    )
    kwargs.update(overrides)
    return PrewarmTask(**kwargs)


# ---------- pure helpers ----------------------------------------------------


def test_bucket_math_is_lockstep_with_provider():
    """Same epoch_seconds // window the OllamaProvider uses — must match."""
    task = _make_task()
    assert task.current_bucket(0) == 0
    assert task.current_bucket(299) == 0
    assert task.current_bucket(300) == 1
    assert task.current_bucket(901) == 3


def test_model_at_cycles_through_pool_within_hour():
    """Within an hour, rotation is a permutation of the pool that repeats.

    The exact sequence isn't input-order — it's a deterministic shuffle keyed
    by the hour bucket. Test the invariant (permutation + cyclical repeat)
    rather than specific symbols, so the assertions survive any Random impl
    change between Python versions.
    """
    task = _make_task(models=["a", "b", "c"], window_seconds=300)
    # 3-model pool × 300s window → 3 buckets per cycle, hour holds 12 buckets
    # = 4 full cycles inside one hour.
    first_cycle = [task.model_at(b) for b in range(3)]
    second_cycle = [task.model_at(b) for b in range(3, 6)]
    assert sorted(first_cycle) == ["a", "b", "c"], "every pool member used"
    assert first_cycle == second_cycle, "same order repeats within the hour"


def test_model_at_reshuffles_across_hour_boundary():
    """The shuffle seed is the hour bucket — order changes at every hour."""
    task = _make_task(
        models=["m0", "m1", "m2", "m3", "m4", "m5", "m6", "m7"],
        window_seconds=300,
    )
    # 8-element pool gives Random plenty of permutation room to differ
    # between consecutive hour seeds (n!=40320 permutations).
    hour0_order = [task.model_at(b) for b in range(8)]
    hour1_order = [task.model_at(b) for b in range(12, 20)]  # bucket 12 = next hour
    assert sorted(hour0_order) == sorted(hour1_order), "same pool both hours"
    assert hour0_order != hour1_order, "fresh shuffle at hour boundary"


def test_requires_at_least_one_model():
    with pytest.raises(ValueError):
        _make_task(models=[])


def test_requires_positive_window():
    with pytest.raises(ValueError):
        _make_task(window_seconds=0)


# ---------- flip handling --------------------------------------------------


class _SendRecorder:
    """Stub for ``PrewarmTask._send`` — records calls without doing I/O."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | int]] = []

    async def __call__(self, model: str, *, keep_alive: str | int) -> None:
        self.calls.append((model, keep_alive))


@pytest.mark.asyncio
async def test_flip_prewarms_next_and_evicts_previous():
    task = _make_task(models=["m0", "m1", "m2", "m3"])
    recorder = _SendRecorder()
    task._send = recorder  # type: ignore[method-assign]

    # bucket 5 is inside hour 0 (window=300, 5*300=1500s). The per-hour
    # shuffle decides which of m0..m3 is at position 5 / 6 / 4 — we don't
    # hard-code that, just assert next-prewarmed and prev-evicted.
    bucket = 5
    expected_next = task.model_at(bucket + 1)
    expected_prev = task.model_at(bucket - 1)
    current = task.model_at(bucket)
    assert expected_next != current and expected_prev != current  # 4-pool, distinct

    await task._handle_flip(bucket)
    # asyncio.create_task schedules; let the loop run them.
    await asyncio.sleep(0)

    assert (expected_next, "30m") in recorder.calls, "pre-warm next"
    assert (expected_prev, 0) in recorder.calls, "evict previous"
    assert len(recorder.calls) == 2


@pytest.mark.asyncio
async def test_flip_skips_when_pool_size_collapses():
    """With a 1-model pool, current==next==prev; nothing to do."""
    task = _make_task(models=["only"])
    recorder = _SendRecorder()
    task._send = recorder  # type: ignore[method-assign]

    await task._handle_flip(7)
    await asyncio.sleep(0)

    assert recorder.calls == []


@pytest.mark.asyncio
async def test_flip_evicts_only_when_distinct_from_current_and_next():
    """With a 2-model pool, prev == next; eviction would unload the next.
    Skip the evict to keep the pre-warmed model loaded.
    """
    task = _make_task(models=["m0", "m1"])
    recorder = _SendRecorder()
    task._send = recorder  # type: ignore[method-assign]

    # bucket 4 -> current=m0, next=m1, prev=m1 (same as next)
    await task._handle_flip(4)
    await asyncio.sleep(0)

    assert ("m1", "30m") in recorder.calls
    assert all(ka != 0 for _, ka in recorder.calls), "must NOT evict m1"


@pytest.mark.asyncio
async def test_tick_first_call_skips_eviction():
    """First tick after startup: pre-warm only — eviction would risk a
    spurious load-unload on a model that may not be resident yet."""
    task = _make_task()
    recorder = _SendRecorder()
    task._send = recorder  # type: ignore[method-assign]

    with patch("app.prewarm.time.time", return_value=300 * 2 + 30):
        await task._tick()
        await asyncio.sleep(0)

    # bucket 2 -> current=m2, next=m3, prev=m1; only pre-warm fires.
    assert recorder.calls == [("m3", "30m")]


@pytest.mark.asyncio
async def test_tick_only_fires_once_per_bucket():
    task = _make_task()
    recorder = _SendRecorder()
    task._send = recorder  # type: ignore[method-assign]

    # Pin time inside bucket 2.
    with patch("app.prewarm.time.time", return_value=300 * 2 + 30):
        await task._tick()
        await task._tick()
        await task._tick()
        await asyncio.sleep(0)

    # 3 ticks, one flip; first tick skips evict -> 1 send.
    assert len(recorder.calls) == 1


@pytest.mark.asyncio
async def test_tick_fires_again_after_bucket_advances_and_evicts():
    """Second flip is the steady-state case: pre-warm next + evict prev."""
    task = _make_task()
    recorder = _SendRecorder()
    task._send = recorder  # type: ignore[method-assign]

    with patch("app.prewarm.time.time", return_value=300 * 2 + 30):
        await task._tick()
    with patch("app.prewarm.time.time", return_value=300 * 3 + 5):
        await task._tick()
    await asyncio.sleep(0)

    # Bucket 2 (first): only pre-warm m3.
    # Bucket 3 (second): pre-warm m0 AND evict m2.
    assert ("m3", "30m") in recorder.calls
    assert ("m0", "30m") in recorder.calls
    assert ("m2", 0) in recorder.calls
    assert len(recorder.calls) == 3


# ---------- env-driven factory ---------------------------------------------


def test_maybe_start_prewarm_disabled_by_env():
    with patch.dict(os.environ, {"OLLAMA_PREWARM_ENABLED": "false"}, clear=False):
        assert maybe_start_prewarm() is None


def test_maybe_start_prewarm_disabled_without_rotation():
    env = {
        "OLLAMA_PREWARM_ENABLED": "true",
        "OLLAMA_ROTATION_ENABLED": "false",
    }
    with patch.dict(os.environ, env, clear=False):
        assert maybe_start_prewarm() is None


def test_maybe_start_prewarm_disabled_when_too_few_models():
    env = {
        "OLLAMA_PREWARM_ENABLED": "true",
        "OLLAMA_ROTATION_ENABLED": "true",
        "OLLAMA_ROTATION_MODELS": "only-one",
    }
    with patch.dict(os.environ, env, clear=False):
        assert maybe_start_prewarm() is None


@pytest.mark.asyncio
async def test_maybe_start_prewarm_returns_running_task():
    env = {
        "OLLAMA_PREWARM_ENABLED": "true",
        "OLLAMA_ROTATION_ENABLED": "true",
        "OLLAMA_ROTATION_MODELS": "a,b,c",
        "OLLAMA_ROTATION_WINDOW_SECONDS": "300",
        "OLLAMA_BASE_URL": "http://stub:11434",
    }
    with patch.dict(os.environ, env, clear=False):
        task = maybe_start_prewarm()
        try:
            assert task is not None
            assert task.models == ["a", "b", "c"]
            assert task.window == 300
            assert task.base_url == "http://stub:11434"
            assert task._task is not None and not task._task.done()
        finally:
            if task:
                await task.stop()
