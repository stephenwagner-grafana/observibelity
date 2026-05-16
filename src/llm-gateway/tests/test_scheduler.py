"""Unit tests for the Ollama model-pool scheduler.

State transitions, sticky routing, session expiry, and the Snapshot.verdict
rule are all pure-Python — no Ollama daemon required. Time and randomness
are injected so the assertions are deterministic.
"""
from __future__ import annotations

import asyncio
import random
from typing import Iterable
from unittest.mock import patch

import pytest

from app.scheduler import (
    DEFAULT_GPU_UTIL_DRAIN_PCT,
    DEFAULT_VRAM_ADD_PCT,
    DEFAULT_VRAM_DRAIN_PCT,
    GPUSensor,
    ModelInstance,
    ModelState,
    OllamaScheduler,
    Snapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Clock:
    """Mutable wall-clock stand-in. Injected via scheduler's ``clock``."""

    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += float(delta)


def _make_scheduler(
    *,
    models: Iterable[str] = ("m0", "m1", "m2", "m3"),
    pool_min: int = 2,
    pool_max: int = 4,
    requests_per_lifecycle: int = 100,
    session_idle_timeout_s: int = 600,
    clock: _Clock | None = None,
    rng: random.Random | None = None,
    sensor: GPUSensor | None = None,
) -> OllamaScheduler:
    s = OllamaScheduler(
        base_url="http://stub:11434",
        models=list(models),
        pool_min=pool_min,
        pool_max=pool_max,
        requests_per_lifecycle=requests_per_lifecycle,
        session_idle_timeout_s=session_idle_timeout_s,
        tick_interval_s=1,
        keep_alive="5m",
        gpu_sensor=sensor,
        clock=clock or _Clock(),
        rng=rng or random.Random(0xCAFE),
    )
    # Block real HTTP — tests inject pool state directly.
    s._enable_io = False
    return s


def _populate(scheduler: OllamaScheduler, *names: str, state: ModelState = ModelState.ACTIVE) -> None:
    """Force the pool to a known shape so we don't depend on tick() ordering."""
    for n in names:
        scheduler.pool[n] = ModelInstance(name=n, state=state, loaded_at=scheduler._clock())
        try:
            scheduler.queue.remove(n)
        except ValueError:
            pass


# ===========================================================================
# State transitions
# ===========================================================================


def test_active_flips_to_draining_at_lifecycle_boundary():
    s = _make_scheduler(requests_per_lifecycle=3)
    _populate(s, "m0")
    inst = s.pool["m0"]

    s.on_request_complete("sess1", "m0")
    s.on_request_complete("sess1", "m0")
    assert inst.state == ModelState.ACTIVE
    assert inst.requests_served == 2

    # The 3rd request hits the budget exactly — flips to DRAINING.
    s.on_request_complete("sess1", "m0")
    assert inst.state == ModelState.DRAINING
    assert inst.requests_served == 3


def test_draining_continues_to_accept_pinned_sessions():
    """A DRAINING model still serves sessions already pinned to it."""
    s = _make_scheduler()
    _populate(s, "m0")
    _populate(s, "m1")
    # Pin sess1 to m0, then drain m0.
    chosen = s.route("sess1")
    s.pool[chosen].state = ModelState.DRAINING
    drained = chosen

    # sess1 should keep getting routed to the SAME draining model.
    assert s.route("sess1") == drained


def test_new_sessions_skip_draining_models():
    s = _make_scheduler(rng=random.Random(42))
    _populate(s, "m_drain", state=ModelState.DRAINING)
    _populate(s, "m_live", state=ModelState.ACTIVE)

    # New session should ALWAYS get the ACTIVE model.
    for i in range(20):
        assert s.route(f"new-{i}") == "m_live"


def test_on_request_complete_safe_when_model_unloaded():
    """Race: model unloaded between route() and completion. Don't crash."""
    s = _make_scheduler()
    # Pool empty; call still has to no-op cleanly.
    s.on_request_complete("sess", "missing-model")  # must not raise


# ===========================================================================
# Sticky routing
# ===========================================================================


def test_sticky_routing_same_session_same_model():
    s = _make_scheduler(rng=random.Random(7))
    _populate(s, "a", "b", "c")
    first = s.route("sess1")
    # Even with a different RNG sample, the pin must hold.
    s._rng = random.Random(99999)
    for _ in range(50):
        assert s.route("sess1") == first


def test_sticky_routing_different_sessions_can_diverge():
    """Two different session_ids may land on different models."""
    # Force 2 ACTIVE; with a wide RNG distribution we should see both used.
    s = _make_scheduler(rng=random.Random(0))
    _populate(s, "a", "b")
    seen: set[str] = set()
    for i in range(100):
        seen.add(s.route(f"sess-{i}"))
    assert seen == {"a", "b"}


def test_below_min_routes_to_only_active():
    """Pool size 1 still serves traffic — pool_min is a target, not a contract."""
    s = _make_scheduler()
    _populate(s, "solo")
    for i in range(10):
        assert s.route(f"sess-{i}") == "solo"


def test_catastrophe_promotes_draining_model():
    """When ACTIVE == 0 and at least one DRAINING exists, promote the youngest."""
    clock = _Clock()
    s = _make_scheduler(clock=clock)
    _populate(s, "old", state=ModelState.DRAINING)
    clock.advance(60)  # younger == loaded later
    _populate(s, "young", state=ModelState.DRAINING)

    chosen = s.route("new-sess")
    assert chosen == "young", "should promote the youngest draining model"
    assert s.pool["young"].state == ModelState.ACTIVE
    # And the promoted model's request counter is reset so it doesn't immediately re-drain.
    assert s.pool["young"].requests_served == 0


def test_empty_pool_returns_none():
    """Truly empty pool -> route returns None -> caller 429s."""
    s = _make_scheduler()
    assert s.route("sess") is None


# ===========================================================================
# Session expiry
# ===========================================================================


def test_session_expires_after_idle_timeout():
    clock = _Clock()
    s = _make_scheduler(
        clock=clock,
        session_idle_timeout_s=600,
    )
    _populate(s, "m0")
    s.route("sess-old")
    # Advance past the 10-min timeout and tick GC.
    clock.advance(601)
    expired = s.expire_sessions()
    assert expired == 1
    assert "sess-old" not in s.session_to_model


def test_session_expiry_unloads_drained_model_with_no_pins():
    """DRAINING model whose last pin expires gets unloaded and queue-rotated."""
    clock = _Clock()
    s = _make_scheduler(clock=clock, session_idle_timeout_s=600)
    _populate(s, "doomed")
    s.route("sess1")
    s.pool["doomed"].state = ModelState.DRAINING
    assert "doomed" in s.pool

    clock.advance(601)
    s.expire_sessions()

    assert "doomed" not in s.pool, "unloaded"
    assert "doomed" in s.queue, "rotated to back of queue"


def test_session_expiry_keeps_active_model():
    """An ACTIVE model with expired sessions is NOT unloaded — only DRAINING ones."""
    clock = _Clock()
    s = _make_scheduler(clock=clock)
    _populate(s, "keep")
    s.route("sess1")
    clock.advance(601)
    s.expire_sessions()
    assert "keep" in s.pool


# ===========================================================================
# Snapshot.verdict
# ===========================================================================


def _green_snapshot(**overrides) -> Snapshot:
    """All-green baseline: under add-line VRAM, low util, low TTFT, slack backlog."""
    kwargs = dict(
        vram_pct=20.0,
        gpu_util_pct=10.0,
        ttft_p95_s=0.5,
        backlog=-4,
        gpu_util_drain_streak_s=0.0,
    )
    kwargs.update(overrides)
    return Snapshot(**kwargs)


def test_verdict_add_when_all_signals_green():
    assert _green_snapshot().verdict() == "add"


def test_verdict_hold_when_vram_in_middle_band():
    snap = _green_snapshot(vram_pct=60.0)  # 50-65 band -> hold
    assert snap.verdict() == "hold"


def test_verdict_drain_when_vram_over_drain_line():
    snap = _green_snapshot(vram_pct=DEFAULT_VRAM_DRAIN_PCT + 5)
    assert snap.verdict() == "drain"


def test_verdict_drain_when_gpu_util_sustained():
    """A brief spike doesn't drain — only sustained overload does."""
    spike = _green_snapshot(
        gpu_util_pct=DEFAULT_GPU_UTIL_DRAIN_PCT + 5,
        gpu_util_drain_streak_s=10.0,  # under sustain threshold
    )
    assert spike.verdict() != "drain"

    sustained = _green_snapshot(
        gpu_util_pct=DEFAULT_GPU_UTIL_DRAIN_PCT + 5,
        gpu_util_drain_streak_s=120.0,  # > 60s sustain
    )
    assert sustained.verdict() == "drain"


def test_verdict_drain_on_ttft_blowout():
    snap = _green_snapshot(ttft_p95_s=10.0)  # >> 2.5x baseline (1.5s)
    assert snap.verdict() == "drain"


def test_verdict_hold_when_backlog_zero():
    """Backlog == 0 means at-capacity but not queueing; hold, don't add."""
    snap = _green_snapshot(backlog=0)
    assert snap.verdict() != "add"


def test_verdict_hold_on_polling_failure_fallback():
    """The fallback() snapshot must resolve to ``hold``."""
    sensor = GPUSensor(prometheus_url="")  # no URL == sensor disabled
    snap = sensor.fallback()
    assert snap.verdict() == "hold"


# ===========================================================================
# GPU sensor
# ===========================================================================


@pytest.mark.asyncio
async def test_gpu_sensor_returns_fallback_when_no_url():
    sensor = GPUSensor(prometheus_url="")
    snap = await sensor.snapshot()
    assert snap.verdict() == "hold"


@pytest.mark.asyncio
async def test_gpu_sensor_handles_query_failures():
    """Prom unreachable -> fallback snapshot."""
    sensor = GPUSensor(prometheus_url="http://nope.invalid:9090")
    snap = await sensor.snapshot()
    assert snap.verdict() == "hold"


def test_gpu_sensor_streak_tracking():
    sensor = GPUSensor(prometheus_url="")
    now = 1000.0
    # Below threshold -> no streak.
    assert sensor._update_drain_streak(50.0, now) == 0.0
    # Above threshold -> streak starts.
    assert sensor._update_drain_streak(90.0, now) == 0.0  # first tick at threshold
    assert sensor._update_drain_streak(90.0, now + 30) == 30.0
    assert sensor._update_drain_streak(90.0, now + 120) == 120.0
    # Falls back below -> streak resets.
    assert sensor._update_drain_streak(50.0, now + 130) == 0.0


# ===========================================================================
# Tick — pool resize integration
# ===========================================================================


class _FakeSensor:
    """Stand-in GPUSensor with a programmable verdict."""

    def __init__(self, snap: Snapshot) -> None:
        self._snap = snap

    async def snapshot(self) -> Snapshot:
        return self._snap

    def fallback(self) -> Snapshot:  # pragma: no cover — only used in error paths
        return Snapshot(vram_pct=0, gpu_util_pct=0, ttft_p95_s=0, backlog=0)


@pytest.mark.asyncio
async def test_tick_loads_aggressively_below_min():
    """tick() loads new models until pool >= min, regardless of verdict."""
    s = _make_scheduler(pool_min=2, sensor=_FakeSensor(_green_snapshot(vram_pct=99.0)))
    # vram=99 means verdict=="drain", but below-min still loads aggressively.
    assert len(s.pool) == 0
    await s.tick()
    assert len(s.pool) == 1
    await s.tick()
    assert len(s.pool) == 2


@pytest.mark.asyncio
async def test_tick_holds_at_max():
    """Even with verdict=add, tick refuses to load past pool_max."""
    s = _make_scheduler(pool_min=2, pool_max=2, sensor=_FakeSensor(_green_snapshot()))
    await s.tick()
    await s.tick()
    await s.tick()
    await s.tick()
    assert len(s.pool) == 2


@pytest.mark.asyncio
async def test_tick_drain_marks_most_loaded_model():
    """verdict=drain flips the highest-served ACTIVE model to DRAINING."""
    s = _make_scheduler(
        pool_min=2, pool_max=4,
        sensor=_FakeSensor(_green_snapshot(
            vram_pct=DEFAULT_VRAM_DRAIN_PCT + 5,  # force drain verdict
        )),
    )
    _populate(s, "a", "b", "c")
    s.pool["a"].requests_served = 50
    s.pool["b"].requests_served = 80
    s.pool["c"].requests_served = 10

    await s.tick()
    # The verdict=drain branch marks the "most loaded" ACTIVE one DRAINING.
    # (b has the most requests, so b should drain.)
    assert s.pool["b"].state == ModelState.DRAINING
    # Pool still has all 3 entries (DRAINING is still loaded).
    assert len(s.pool) == 3
