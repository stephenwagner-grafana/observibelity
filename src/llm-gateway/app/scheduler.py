"""Dynamic Ollama model-pool scheduler.

Replaces the old fixed-window rotation (``prewarm.py`` + ``providers/ollama.py``
bucket math) with a state-machine that loads models on demand, drains them
after a per-model request budget, and lets the GPU's headroom drive pool
size.

Lifecycle for a single model
----------------------------
::

    queue (back) ──► LOADING ──► ACTIVE ──► DRAINING ──► (unload) ──► queue (back)
                                  │                          │
                                  │                          └── last sticky session expires
                                  └── 100 requests served

* **LOADING** — the scheduler asked Ollama to pull the weights into VRAM.
  Not yet eligible for new conversations. (Today this is a synthetic state
  — Ollama loads on first /api/chat request, so we mark ACTIVE as soon as
  we promote.)
* **ACTIVE** — accepts new session assignments. Counts every completed
  request; at exactly ``requests_per_lifecycle`` (default 100) flips to
  DRAINING.
* **DRAINING** — does NOT accept new session assignments, but continues
  serving requests for sessions already pinned to it. When the last sticky
  session expires (10-min idle), the scheduler unloads the model (Ollama
  releases VRAM via ``keep_alive`` ageing) and pushes it to the back of
  the queue.

Sticky routing
--------------
The first request for a new ``session_id`` picks a random ACTIVE model and
records the binding. Every subsequent request for the same session_id
goes to that model — *even after it drains* — until the session is
idle for ``session_idle_timeout_s`` (default 600s = 10 min).

If a draining model holds the only existing pin for a session and the
session expires, the scheduler unloads the model and rotates the queue.

Below-min behavior
------------------
The scheduler tries hard to keep ``pool.min`` (default 2) models ACTIVE.
But VRAM is a hard ceiling — a 30B model needs ~18GB and won't fit
alongside a second one inside the 50% cap. If only 1 ACTIVE model fits,
the pool happily runs with 1 and routes everything to it. If
``ACTIVE == 0`` (e.g. all loaded models are draining), the scheduler
promotes the youngest DRAINING model so new sessions still get answered.
Only if no model is loaded at all does ``route()`` return ``None``
(translated to a 429 with reason ``ollama_pool_empty``).

Saturation thresholds — see ``Snapshot.verdict``
------------------------------------------------
Four signals decide whether to add / hold / drain. The thresholds were
picked conservatively because the operator wants headroom; tune via env.

GPU sensor
----------
``GPUSensor.snapshot()`` is a pure-data helper around four PromQL queries.
On any failure (Prometheus unreachable, missing series, bad credentials)
it returns a "green-but-cautious" snapshot — vram_pct=0, gpu_util_pct=0,
ttft_p95_s=0, backlog=0 — which makes ``verdict()`` return ``"hold"``.
That keeps the scheduler from making bad decisions on bad data.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

import httpx

log = logging.getLogger("llm_gateway.scheduler")


# ---------------------------------------------------------------------------
# Env-driven knobs (defaults match values.yaml so unit tests don't need Helm)
# ---------------------------------------------------------------------------

DEFAULT_POOL_MIN = 2
DEFAULT_POOL_MAX = 4
DEFAULT_REQUESTS_PER_LIFECYCLE = 100
DEFAULT_SESSION_IDLE_TIMEOUT_S = 600  # 10 minutes
DEFAULT_TICK_INTERVAL_S = 10

# VRAM thresholds (% of 32GB on the .240 5090)
DEFAULT_VRAM_ADD_PCT = 50.0  # below this and we MAY add (combined with other signals)
DEFAULT_VRAM_HOLD_PCT = 65.0  # above this we hold
DEFAULT_VRAM_DRAIN_PCT = 70.0  # above this we drain
# Headroom in GB the next model must fit under once it loads.
DEFAULT_VRAM_CUSHION_GB = 2.0

# GPU compute util thresholds (5m avg)
DEFAULT_GPU_UTIL_ADD_PCT = 60.0
DEFAULT_GPU_UTIL_HOLD_PCT = 75.0
DEFAULT_GPU_UTIL_DRAIN_PCT = 80.0
# How long sustained over-util must hold before we drain.
DEFAULT_GPU_UTIL_DRAIN_SUSTAIN_S = 60.0

# TTFT ratios vs baseline
DEFAULT_TTFT_ADD_RATIO = 1.3   # <= 1.3x baseline = green
DEFAULT_TTFT_HOLD_RATIO = 2.0  # 1.3-2x = hold
DEFAULT_TTFT_DRAIN_RATIO = 2.5 # > 2.5x = drain
# What we call "baseline" for the first 5m after boot when there's nothing
# to compare to. Tunable so deployment-specific baselines can be wired in.
DEFAULT_TTFT_BASELINE_S = 1.5

# Default total VRAM on the host (32GB for the .240 5090). Operators can
# override via OLLAMA_POOL_VRAM_TOTAL_GB if they redeploy on a different card.
DEFAULT_VRAM_TOTAL_GB = 32.0


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class ModelState(Enum):
    """States a pool member can occupy. See module docstring for transitions."""

    LOADING = "loading"
    ACTIVE = "active"
    DRAINING = "draining"


@dataclass
class ModelInstance:
    """One row of the live pool.

    ``loaded_at`` is wall-clock seconds; used for "youngest draining" tie-break
    when we need to promote a draining model out of catastrophe (ACTIVE == 0).
    ``requests_served`` is a per-cycle counter — every transition to DRAINING
    resets it to 0 so re-loaded models start fresh.
    """

    name: str
    state: ModelState
    requests_served: int = 0
    assigned_sessions: set[str] = field(default_factory=set)
    loaded_at: float = field(default_factory=time.time)


@dataclass
class Snapshot:
    """Point-in-time view of GPU + gateway saturation.

    Every field is "the freshest number we know right now". A polling
    failure short-circuits to a green-but-cautious snapshot via
    ``GPUSensor.fallback()``; ``verdict()`` resolves THAT to ``"hold"``,
    which is the safest no-op.
    """

    vram_pct: float
    gpu_util_pct: float
    ttft_p95_s: float
    backlog: int
    # Wall-clock seconds the GPU has been over the drain util threshold —
    # the "sustained > 80% for 60s" rule needs hysteresis, so the sensor
    # tracks the streak and stamps it here. 0 == no streak.
    gpu_util_drain_streak_s: float = 0.0

    # Thresholds used to compute the verdict — kept on the snapshot so a
    # dashboard can show the value AND the line it's compared against
    # without re-deriving config in the panel.
    vram_add_pct: float = DEFAULT_VRAM_ADD_PCT
    vram_hold_pct: float = DEFAULT_VRAM_HOLD_PCT
    vram_drain_pct: float = DEFAULT_VRAM_DRAIN_PCT
    gpu_util_add_pct: float = DEFAULT_GPU_UTIL_ADD_PCT
    gpu_util_hold_pct: float = DEFAULT_GPU_UTIL_HOLD_PCT
    gpu_util_drain_pct: float = DEFAULT_GPU_UTIL_DRAIN_PCT
    gpu_util_drain_sustain_s: float = DEFAULT_GPU_UTIL_DRAIN_SUSTAIN_S
    ttft_baseline_s: float = DEFAULT_TTFT_BASELINE_S
    ttft_add_ratio: float = DEFAULT_TTFT_ADD_RATIO
    ttft_hold_ratio: float = DEFAULT_TTFT_HOLD_RATIO
    ttft_drain_ratio: float = DEFAULT_TTFT_DRAIN_RATIO

    def verdict(self) -> str:
        """Reduce 4 signals to a single ``"add"|"hold"|"drain"`` verdict.

        Rules — DRAIN wins ties, ADD requires ALL signals green:

        * **drain** if ANY of:
          - vram_pct > vram_drain_pct (70%)
          - gpu_util_pct > gpu_util_drain_pct AND streak > gpu_util_drain_sustain_s
            (the sustained-overload check — a momentary spike doesn't drain)
          - ttft_p95_s > ttft_drain_ratio * ttft_baseline_s
          - backlog growing past zero AND the streak has been > sustain_s
            (we don't track backlog hysteresis separately, so we lean on the
            GPU streak as a proxy for "this has been bad for a while")
        * **add** if ALL of:
          - vram_pct < vram_add_pct (50%)
          - gpu_util_pct <= gpu_util_add_pct (60%)
          - ttft_p95_s <= ttft_add_ratio * ttft_baseline_s
          - backlog < 0 (slots available)
        * **hold** otherwise.
        """
        ttft_drain_line = self.ttft_drain_ratio * self.ttft_baseline_s
        ttft_add_line = self.ttft_add_ratio * self.ttft_baseline_s

        # DRAIN — any red flag.
        if self.vram_pct > self.vram_drain_pct:
            return "drain"
        if (
            self.gpu_util_pct > self.gpu_util_drain_pct
            and self.gpu_util_drain_streak_s > self.gpu_util_drain_sustain_s
        ):
            return "drain"
        if self.ttft_p95_s > ttft_drain_line and self.ttft_baseline_s > 0:
            return "drain"
        if (
            self.backlog > 0
            and self.gpu_util_drain_streak_s > self.gpu_util_drain_sustain_s
        ):
            return "drain"

        # ADD — all signals green.
        if (
            self.vram_pct < self.vram_add_pct
            and self.gpu_util_pct <= self.gpu_util_add_pct
            and (self.ttft_p95_s <= ttft_add_line or self.ttft_baseline_s == 0)
            and self.backlog < 0
        ):
            return "add"

        return "hold"


# ---------------------------------------------------------------------------
# GPU sensor — polls Prometheus for live VRAM / util / TTFT / backlog
# ---------------------------------------------------------------------------

class GPUSensor:
    """Snapshot provider that reads live signals from Prometheus.

    Construction is free — the constructor just stashes config. ``snapshot()``
    is the I/O entry-point and is fully defensive: any failure returns a
    "hold-equivalent" snapshot so the scheduler stays inert on bad data.

    Metric names default to the live series in the .240 cluster
    (``nvidia_gpu_*`` from the nvidia-smi exporter) because DCGM is NOT
    scraped here. The PromQL is overridable via env so a different cluster
    can swap in DCGM_FI_* without code changes.
    """

    def __init__(
        self,
        *,
        prometheus_url: str | None = None,
        bearer_token: str | None = None,
        vram_total_gb: float = DEFAULT_VRAM_TOTAL_GB,
        # PromQL expressions — defaults work against nvidia-smi-exporter +
        # the gateway's own gen_ai_client_time_to_first_token histogram.
        vram_pct_query: str | None = None,
        gpu_util_query: str | None = None,
        ttft_p95_query: str | None = None,
        timeout_s: float = 5.0,
        # Pure-function provider state inspector — the scheduler passes a
        # lambda returning ``(in_flight, capacity)`` so the sensor can derive
        # backlog without coupling to the ollama provider type directly.
        in_flight_getter: callable | None = None,
        capacity: int = 8,
    ) -> None:
        self.prometheus_url = (prometheus_url or "").rstrip("/")
        self.bearer_token = bearer_token or ""
        self.vram_total_gb = float(vram_total_gb)
        # Defaults reflect what's ACTUALLY scraped in the .240 cluster:
        # nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes and
        # nvidia_gpu_utilization_gpu_ratio (0-1) — multiplied by 100 to give
        # a percentage. DCGM_FI_* is not present in this cluster. Operators
        # can override via constructor arg OR env var when deploying against
        # a DCGM-scraped or otherwise-instrumented fleet.
        self.vram_pct_query = (
            vram_pct_query
            or os.environ.get("OLLAMA_POOL_VRAM_QUERY")
            or "100 * (nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes)"
        )
        self.gpu_util_query = (
            gpu_util_query
            or os.environ.get("OLLAMA_POOL_UTIL_QUERY")
            or "100 * avg_over_time(nvidia_gpu_utilization_gpu_ratio[5m])"
        )
        self.ttft_p95_query = (
            ttft_p95_query
            or os.environ.get("OLLAMA_POOL_TTFT_QUERY")
            or (
                'histogram_quantile(0.95, sum by (le) ('
                'rate(gen_ai_client_time_to_first_token_seconds_bucket[5m])))'
            )
        )
        self.timeout_s = float(timeout_s)
        self.in_flight_getter = in_flight_getter
        self.capacity = int(capacity)
        self._drain_streak_started_at: float | None = None

    # ------------------ pure helpers ------------------

    def _update_drain_streak(self, gpu_util_pct: float, now: float) -> float:
        """Track sustained-overload window. Returns the current streak length.

        Streak starts when util crosses the drain line, ends when it falls
        back below. Pure-function but uses ``self`` for state, which the
        scheduler treats as opaque.
        """
        if gpu_util_pct > DEFAULT_GPU_UTIL_DRAIN_PCT:
            if self._drain_streak_started_at is None:
                self._drain_streak_started_at = now
            return now - self._drain_streak_started_at
        self._drain_streak_started_at = None
        return 0.0

    def fallback(self) -> Snapshot:
        """Green-but-cautious snapshot used when Prometheus is unreachable.

        Values are chosen so ``verdict()`` returns ``"hold"`` (vram & util
        below add-line but TTFT/backlog not strictly green, so the ALL-green
        gate doesn't fire). The scheduler reads "hold" as "do nothing this
        tick" — exactly right when we can't see the GPU.
        """
        return Snapshot(
            vram_pct=0.0,
            gpu_util_pct=0.0,
            ttft_p95_s=0.0,
            backlog=0,  # 0 == zero-headroom; verdict needs < 0 to add
            gpu_util_drain_streak_s=0.0,
        )

    async def _query_scalar(
        self, client: httpx.AsyncClient, expr: str
    ) -> float | None:
        """Single PromQL instant query → scalar value, or None on failure.

        Picks the FIRST result's value if a query returns multiple series
        (so per-GPU metrics on a multi-GPU host collapse to "the first GPU").
        Tune the query if you want sum() or max() across cards.
        """
        if not self.prometheus_url:
            return None
        headers = {}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        try:
            r = await client.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": expr},
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            result = (data.get("data") or {}).get("result") or []
            if not result:
                return None
            value = (result[0].get("value") or [None, None])[1]
            return float(value) if value is not None else None
        except Exception as exc:  # noqa: BLE001 — sensor must never raise.
            log.debug("PromQL query failed: expr=%r err=%s", expr, exc)
            return None

    async def snapshot(self) -> Snapshot:
        """Read all four signals and assemble a Snapshot.

        Order of operations is independent — we issue queries serially to
        keep the function easy to mock, but a future optimization could
        ``asyncio.gather`` them.
        """
        now = time.time()
        if not self.prometheus_url:
            # Sensor not configured — emit fallback so the scheduler stays inert.
            return self.fallback()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                vram_pct = await self._query_scalar(client, self.vram_pct_query)
                gpu_util = await self._query_scalar(client, self.gpu_util_query)
                ttft_p95 = await self._query_scalar(client, self.ttft_p95_query)
        except Exception as exc:  # noqa: BLE001
            log.warning("GPU sensor snapshot failed (Prom unreachable?): %s", exc)
            return self.fallback()

        # If ANY of the headline gauges came back None, we don't have enough
        # to make a decision — fall back to hold-equivalent rather than
        # plugging in zeros that might tip ADD.
        if vram_pct is None or gpu_util is None:
            log.debug("GPU sensor: missing core metrics; emitting fallback")
            return self.fallback()
        if ttft_p95 is None:
            ttft_p95 = 0.0  # no traffic yet ≠ slow; treat as "no opinion"

        # Local backlog — synchronous read of the ollama provider's
        # in-flight counter (single-threaded asyncio, race-free).
        backlog = 0
        if self.in_flight_getter is not None:
            try:
                in_flight = int(self.in_flight_getter() or 0)
            except Exception:  # noqa: BLE001
                in_flight = 0
            backlog = in_flight - self.capacity

        streak = self._update_drain_streak(gpu_util, now)
        return Snapshot(
            vram_pct=float(vram_pct),
            gpu_util_pct=float(gpu_util),
            ttft_p95_s=float(ttft_p95),
            backlog=int(backlog),
            gpu_util_drain_streak_s=streak,
        )


# ---------------------------------------------------------------------------
# OllamaScheduler — the state machine
# ---------------------------------------------------------------------------

class OllamaScheduler:
    """Pool of Ollama models with state-machine'd lifecycle + sticky routing.

    Hot path: ``route(session_id)`` returns a model name (or None for 429).
    Cold path: ``tick()`` runs every 10s and may load/unload models based on
    ``GPUSensor`` verdicts.

    Threading: the scheduler assumes single-threaded asyncio. All mutations
    happen on the event-loop thread — no locks needed. Tests can call
    ``route``/``on_request_complete``/``tick`` synchronously where they're
    pure (tick is async only because of the sensor).
    """

    def __init__(
        self,
        *,
        base_url: str,
        models: list[str],
        pool_min: int = DEFAULT_POOL_MIN,
        pool_max: int = DEFAULT_POOL_MAX,
        requests_per_lifecycle: int = DEFAULT_REQUESTS_PER_LIFECYCLE,
        session_idle_timeout_s: int = DEFAULT_SESSION_IDLE_TIMEOUT_S,
        tick_interval_s: int = DEFAULT_TICK_INTERVAL_S,
        keep_alive: str = "5m",
        http_timeout_s: float = 30.0,
        gpu_sensor: GPUSensor | None = None,
        # Injectable clock + RNG for deterministic tests.
        clock: callable | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if not models:
            raise ValueError("OllamaScheduler requires at least one model")
        if pool_min < 1 or pool_max < pool_min:
            raise ValueError("invalid pool_min/pool_max")

        self.base_url = base_url.rstrip("/")
        self.pool_min = int(pool_min)
        self.pool_max = int(pool_max)
        self.requests_per_lifecycle = int(requests_per_lifecycle)
        self.session_idle_timeout_s = float(session_idle_timeout_s)
        self.tick_interval_s = max(1, int(tick_interval_s))
        self.keep_alive = keep_alive
        self.http_timeout_s = float(http_timeout_s)
        self.gpu_sensor = gpu_sensor

        self.pool: dict[str, ModelInstance] = {}
        # Queue of models waiting to be loaded. The constructor seeds with
        # the configured order; tick() rotates drained models to the back.
        self.queue: list[str] = list(models)
        # session_id -> (model_name, last_seen_ts)
        self.session_to_model: dict[str, tuple[str, float]] = {}

        self._clock = clock or time.time
        self._rng = rng or random.Random()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        # Latest snapshot — exposed so OTel observable gauges can read it.
        self._last_snapshot: Snapshot | None = None
        self._last_verdict: str = "hold"
        # If True, every tick is allowed to mutate the pool. If False, the
        # scheduler is in "observe only" mode (used by tests that want to
        # call tick() without firing real Ollama loads).
        self._enable_io = True

    # ===================================================================
    # Hot path — request routing
    # ===================================================================

    def route(self, session_id: str) -> str | None:
        """Return the model name to use for ``session_id`` (or None for 429).

        Resolution order:

        1. If session already pinned AND its model is still loaded → reuse
           the pin (even if the model is DRAINING — that's the whole point
           of sticky routing).
        2. Otherwise pick a random ACTIVE model and pin.
        3. If no ACTIVE model exists, **promote** a DRAINING model so new
           sessions still get served. The youngest draining model is
           preferred (most recently loaded == warmest).
        4. If the pool is completely empty, return None.

        Empty-string session_id is treated as a unique-per-request session
        (so eval-judge replays and one-shot curls don't all pin to one
        model). The pin is still recorded; ``expire_sessions()`` will GC
        it after the idle timeout.
        """
        now = self._clock()

        pin = self.session_to_model.get(session_id) if session_id else None
        if pin is not None:
            pinned_model, _ = pin
            inst = self.pool.get(pinned_model)
            if inst is not None:
                # Refresh last-seen and reuse the pin regardless of state.
                self.session_to_model[session_id] = (pinned_model, now)
                inst.assigned_sessions.add(session_id)
                return pinned_model
            # Pin model is no longer loaded — fall through to re-assignment.

        active = [m for m in self.pool.values() if m.state == ModelState.ACTIVE]
        if not active:
            # Catastrophe: no ACTIVE models. Promote the youngest DRAINING.
            draining = [m for m in self.pool.values() if m.state == ModelState.DRAINING]
            if draining:
                draining.sort(key=lambda m: m.loaded_at, reverse=True)
                promoted = draining[0]
                promoted.state = ModelState.ACTIVE
                # Reset the per-cycle counter so the promoted model gets a
                # fresh budget — otherwise it'd flip straight back to drain
                # on the very next request.
                promoted.requests_served = 0
                log.warning(
                    "scheduler catastrophe: no ACTIVE models; promoted %s from DRAINING",
                    promoted.name,
                )
                active = [promoted]

        if not active:
            # Truly empty pool — caller should 429 with ollama_pool_empty.
            return None

        chosen = self._rng.choice(active)
        chosen.assigned_sessions.add(session_id)
        self.session_to_model[session_id] = (chosen.name, now)
        return chosen.name

    def on_request_complete(self, session_id: str, model: str) -> None:
        """Bump request counter; flip to DRAINING when budget hits 0.

        ``session_id`` is kept in the signature even though we don't use it
        today — gives us a clean place to add per-session telemetry later
        (e.g. fairness counters) without changing every call site.
        """
        inst = self.pool.get(model)
        if inst is None:
            # Race: model was unloaded between route() and completion. The
            # request already succeeded; nothing to bump.
            return
        inst.requests_served += 1
        if (
            inst.state == ModelState.ACTIVE
            and inst.requests_served >= self.requests_per_lifecycle
        ):
            inst.state = ModelState.DRAINING
            log.info(
                "scheduler: %s reached %d requests; state -> DRAINING (%d pinned sessions)",
                inst.name, inst.requests_served, len(inst.assigned_sessions),
            )

    # ===================================================================
    # Bookkeeping
    # ===================================================================

    def expire_sessions(self) -> int:
        """GC stale session pins. Returns the count expired.

        When a DRAINING model loses its last pin, the scheduler unloads it
        and pushes the name to the back of the queue so it can be re-loaded
        later when capacity is needed.
        """
        now = self._clock()
        cutoff = now - self.session_idle_timeout_s
        expired: list[str] = []
        for sid, (model, last_seen) in list(self.session_to_model.items()):
            if last_seen < cutoff:
                expired.append(sid)
                inst = self.pool.get(model)
                if inst is not None:
                    inst.assigned_sessions.discard(sid)
        for sid in expired:
            self.session_to_model.pop(sid, None)

        # Sweep DRAINING models that have no remaining pins.
        for name, inst in list(self.pool.items()):
            if (
                inst.state == ModelState.DRAINING
                and not inst.assigned_sessions
            ):
                log.info("scheduler: %s drained empty; unloading", name)
                self._unload(name)
        return len(expired)

    def _unload(self, name: str) -> None:
        """Remove a model from the pool and push it to the back of the queue.

        Doesn't actively issue an Ollama keep_alive=0 — the daemon ages
        idle models out within ~5 minutes once we stop sending requests
        to them (per the parallel agent's keep_alive=5m change on .240).
        Active eviction is available via _evict_async() if needed.
        """
        self.pool.pop(name, None)
        if name not in self.queue:
            self.queue.append(name)

    # ===================================================================
    # Cold path — tick(): GPU-driven pool resize
    # ===================================================================

    async def tick(self) -> None:
        """One scheduler iteration. Safe to call from a test loop.

        Order:
          1. expire_sessions (free up DRAINING models that have no pins)
          2. sensor.snapshot() → verdict
          3. apply verdict:
             - "add"   and pool < min → load next from queue (always)
             - "add"   and pool < max → load next from queue (capacity headroom)
             - "hold"  → no-op
             - "drain" → mark the most-loaded ACTIVE model DRAINING
                         (so it stops taking NEW sessions while still
                          serving its existing ones)
        """
        self.expire_sessions()

        snapshot = await self._safe_snapshot()
        self._last_snapshot = snapshot
        verdict = snapshot.verdict()
        self._last_verdict = verdict

        loaded = self._loaded_count()
        active = self._active_count()

        log.debug(
            "scheduler tick: loaded=%d active=%d queue=%d verdict=%s "
            "vram=%.1f%% util=%.1f%% ttft_p95=%.2fs backlog=%d",
            loaded, active, len(self.queue), verdict,
            snapshot.vram_pct, snapshot.gpu_util_pct,
            snapshot.ttft_p95_s, snapshot.backlog,
        )

        # 1) Below-min target — load aggressively regardless of verdict.
        if loaded < self.pool_min and self.queue:
            await self._load_next()
            return

        # 2) Verdict-driven resize.
        if verdict == "add" and loaded < self.pool_max and self.queue:
            await self._load_next()
            return

        if verdict == "drain" and active > self.pool_min - 1:
            # Force-drain the model with the highest requests_served (the
            # most "burned-in" one) so the next eviction is reasonably
            # graceful — its sessions are most likely also winding down.
            actives = [m for m in self.pool.values() if m.state == ModelState.ACTIVE]
            if actives:
                actives.sort(key=lambda m: m.requests_served, reverse=True)
                target = actives[0]
                target.state = ModelState.DRAINING
                log.info(
                    "scheduler force-drain (verdict=drain): %s (served=%d)",
                    target.name, target.requests_served,
                )

    async def _safe_snapshot(self) -> Snapshot:
        if self.gpu_sensor is None:
            # No sensor configured — emit hold-equivalent.
            return Snapshot(
                vram_pct=0.0,
                gpu_util_pct=0.0,
                ttft_p95_s=0.0,
                backlog=0,
            )
        try:
            return await self.gpu_sensor.snapshot()
        except Exception as exc:  # noqa: BLE001
            log.warning("gpu_sensor.snapshot raised; falling back: %s", exc)
            return self.gpu_sensor.fallback()

    async def _load_next(self) -> None:
        """Pull the next model from the queue and load it into the pool.

        On the daemon side this is a no-op until the model first answers a
        request (Ollama is lazy). We still register the instance as ACTIVE
        immediately so route() can hand traffic to it. If the pre-warm POST
        fails we leave the model in the pool — the first real request will
        either succeed (Ollama loaded it on demand) or fail loudly.
        """
        if not self.queue:
            return
        name = self.queue.pop(0)
        if name in self.pool:
            # Already loaded — ignore + skip the warm-up.
            return
        inst = ModelInstance(
            name=name,
            state=ModelState.ACTIVE,
            loaded_at=self._clock(),
        )
        self.pool[name] = inst
        log.info(
            "scheduler: load %s (pool size %d/%d, queue depth %d)",
            name, len(self.pool), self.pool_max, len(self.queue),
        )
        if self._enable_io:
            await self._warmup_async(name)

    async def _warmup_async(self, model: str) -> None:
        """Fire a tiny /api/chat POST so Ollama actually GPU-loads weights.

        Without this, the FIRST real /v1/complete after promotion eats ~3s of
        model-load time as TTFT. We POST to /api/chat (same endpoint real
        traffic uses) with the same ``num_ctx`` (so the KV-cache aligns with
        subsequent requests instead of being thrown away).

        Fire-and-forget: errors are logged and dropped. Failure here doesn't
        un-promote the model — the first real /v1/complete will re-attempt.
        Short 5s timeout so a stuck daemon doesn't stall the scheduler tick.
        """
        # Read OLLAMA_NUM_CTX at call time (not import time) so tests that
        # tweak the env var see the override. The ollama provider applies
        # the same default if the env is unset.
        try:
            num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "2048"))
        except ValueError:
            num_ctx = 2048
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "."}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": 1, "num_ctx": num_ctx},
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(f"{self.base_url}/api/chat", json=payload)
                if r.status_code >= 400:
                    log.warning(
                        "scheduler warmup failed: model=%s status=%s body=%s",
                        model, r.status_code, r.text[:200],
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("scheduler warmup error: model=%s err=%s", model, exc)

    # ===================================================================
    # OTel-friendly accessors (callbacks read these on the metrics thread)
    # ===================================================================

    def _loaded_count(self) -> int:
        return len(self.pool)

    def _active_count(self) -> int:
        return sum(1 for m in self.pool.values() if m.state == ModelState.ACTIVE)

    def _draining_count(self) -> int:
        return sum(1 for m in self.pool.values() if m.state == ModelState.DRAINING)

    def snapshot_for_metrics(self) -> dict[str, Any]:
        """Read-only dict the OTel observable-gauge callbacks consume.

        Pure read; safe to call from any thread because everything in here
        is either an int or a string copy.
        """
        snap = self._last_snapshot
        return {
            "loaded": self._loaded_count(),
            "active": self._active_count(),
            "draining": self._draining_count(),
            "queue_depth": len(self.queue),
            "pool_min": self.pool_min,
            "pool_max": self.pool_max,
            "verdict": self._last_verdict,
            "snapshot": snap,
            "models": [
                {
                    "name": m.name,
                    "state": m.state.value,
                    "requests_served": m.requests_served,
                    "assigned_sessions": len(m.assigned_sessions),
                }
                for m in self.pool.values()
            ],
        }

    # ===================================================================
    # Background task lifecycle
    # ===================================================================

    async def _run(self) -> None:
        log.info(
            "scheduler started: pool min=%d max=%d req/cycle=%d idle=%ds tick=%ds",
            self.pool_min, self.pool_max, self.requests_per_lifecycle,
            int(self.session_idle_timeout_s), self.tick_interval_s,
        )
        # First tick happens immediately so the pool fills on boot rather
        # than waiting tick_interval_s seconds for the first batch of users.
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 — never let this kill the gateway
                log.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.tick_interval_s
                )
            except asyncio.TimeoutError:
                pass
        log.info("scheduler stopped")

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


# ---------------------------------------------------------------------------
# Env-driven factory — used by main.py during lifespan startup
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _parse_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [m.strip() for m in raw.split(",") if m.strip()]


def maybe_start_scheduler(
    in_flight_getter: callable | None = None,
) -> OllamaScheduler | None:
    """Read env + build + start a scheduler, or return None if disabled.

    Env vars (defaults match values.yaml::llmGateway.providers.ollama.pool):

      OLLAMA_POOL_ENABLED=true
      OLLAMA_POOL_MODELS=<csv>          # candidate model list
      OLLAMA_POOL_MIN=2
      OLLAMA_POOL_MAX=4
      OLLAMA_POOL_REQUESTS_PER_LIFECYCLE=100
      OLLAMA_POOL_SESSION_IDLE_TIMEOUT_S=600
      OLLAMA_POOL_TICK_INTERVAL_S=10
      OLLAMA_KEEP_ALIVE=5m              # passed through to warm-up calls
      OLLAMA_BASE_URL=http://...
      OLLAMA_POOL_PROMETHEUS_URL=       # GPU sensor data source
      OLLAMA_POOL_PROMETHEUS_TOKEN=     # bearer (optional)
      OLLAMA_POOL_VRAM_TOTAL_GB=32
      OLLAMA_POOL_CAPACITY=8            # NUM_PARALLEL on .240
    """
    if not _env_bool("OLLAMA_POOL_ENABLED", True):
        log.info("OLLAMA_POOL_ENABLED=false; scheduler disabled")
        return None
    models = _parse_csv(os.environ.get("OLLAMA_POOL_MODELS"))
    if not models:
        # Back-compat: if the old rotation env is still set, lift it into
        # the pool config so existing Helm values keep working.
        models = _parse_csv(os.environ.get("OLLAMA_ROTATION_MODELS"))
    if not models:
        log.info("OLLAMA_POOL_MODELS empty; scheduler disabled")
        return None

    base_url = (
        os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
    ).rstrip("/")

    sensor = GPUSensor(
        prometheus_url=os.environ.get("OLLAMA_POOL_PROMETHEUS_URL"),
        bearer_token=os.environ.get("OLLAMA_POOL_PROMETHEUS_TOKEN"),
        vram_total_gb=_env_float("OLLAMA_POOL_VRAM_TOTAL_GB", DEFAULT_VRAM_TOTAL_GB),
        in_flight_getter=in_flight_getter,
        capacity=_env_int("OLLAMA_POOL_CAPACITY", 8),
    )

    scheduler = OllamaScheduler(
        base_url=base_url,
        models=models,
        pool_min=_env_int("OLLAMA_POOL_MIN", DEFAULT_POOL_MIN),
        pool_max=_env_int("OLLAMA_POOL_MAX", DEFAULT_POOL_MAX),
        requests_per_lifecycle=_env_int(
            "OLLAMA_POOL_REQUESTS_PER_LIFECYCLE", DEFAULT_REQUESTS_PER_LIFECYCLE
        ),
        session_idle_timeout_s=_env_int(
            "OLLAMA_POOL_SESSION_IDLE_TIMEOUT_S", DEFAULT_SESSION_IDLE_TIMEOUT_S
        ),
        tick_interval_s=_env_int(
            "OLLAMA_POOL_TICK_INTERVAL_S", DEFAULT_TICK_INTERVAL_S
        ),
        keep_alive=os.environ.get("OLLAMA_KEEP_ALIVE", "5m"),
        gpu_sensor=sensor,
    )
    scheduler.start()
    return scheduler


__all__ = [
    "DEFAULT_POOL_MAX",
    "DEFAULT_POOL_MIN",
    "DEFAULT_REQUESTS_PER_LIFECYCLE",
    "DEFAULT_SESSION_IDLE_TIMEOUT_S",
    "DEFAULT_TICK_INTERVAL_S",
    "GPUSensor",
    "ModelInstance",
    "ModelState",
    "OllamaScheduler",
    "Snapshot",
    "maybe_start_scheduler",
]
