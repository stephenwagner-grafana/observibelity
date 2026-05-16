"""Admission control for the default lane of the llm-gateway.

The default lane (loadgen + non-interactive callers) is routed by a **tiered
probabilistic sampler** on the Claude side + a saturation gate on the Ollama
side. The interactive lane is *not* admission-controlled — those requests
bypass this module entirely and are forced to Claude by the dispatcher.

Per-request flow (caller-driven, see ``main.complete``):

  1. Roll a die: P(target=anthropic) == ``claude_sample_rate(default_spend)``.
  2. Else target = ollama.
  3. If target == ollama: run ``ollama_admit``. If denied → 429
     (``reason=ollama_saturated``). No fallback to Claude.
  4. If target == anthropic: route unconditionally — the dice did the
     throttling. EXCEPTION: if today's default-lane spend somehow climbs
     past ``CLAUDE_SANITY_SENTINEL_USD`` ($200), hard-stop with
     ``reason=claude_sanity_sentinel``. This is a paranoia ceiling, not an
     operating limit; it should never fire.

Sampling table (each $20 above the base cuts the rate by 10x):

  $0   – $40   → 0.10        (10%)
  $40  – $60   → 0.01        (1%)
  $60  – $80   → 0.001       (0.1%)
  $80  – $100  → 0.0001      (0.01%)
  $100 – $120  → 0.00001     (0.001%)
  $120+        → 0.000001    (0.0001%; asymptotic floor)

State dict shape consumed by ``claude_admit_default``::

  {
    "default_spend_usd": float,    # today's default-lane Claude spend
  }

State dict shape consumed by ``ollama_admit``::

  {
    "in_flight": int,              # live in-flight count on this gateway pod
    "saturation_threshold": int,   # OLLAMA_SATURATION_THRESHOLD (default 8)
  }
"""
from __future__ import annotations

import os
from typing import Any


# Sanity sentinel — a paranoia ceiling on default-lane Claude spend. Under
# the tiered sampler the probability of getting here is vanishingly small,
# but if something pathological happens (e.g. the sampler is bypassed by a
# bug, or per-call cost is multiple dollars), this is the hard stop.
CLAUDE_SANITY_SENTINEL_USD = float(
    os.environ.get("CLAUDE_SANITY_SENTINEL_USD", "200.0")
)

# Tiered-sampler tunables. The brief settled on a 10% base rate that decays
# by 10x for every $20 of default-lane spend above $40. Operators can lift
# the knobs if they want a different curve.
CLAUDE_SAMPLE_TIER_BASE = float(
    os.environ.get("CLAUDE_SAMPLE_TIER_BASE", "40.0")
)
CLAUDE_SAMPLE_TIER_WIDTH = float(
    os.environ.get("CLAUDE_SAMPLE_TIER_WIDTH", "20.0")
)
CLAUDE_SAMPLE_BASE_RATE = float(
    os.environ.get("CLAUDE_SAMPLE_BASE_RATE", "0.10")
)

# Mirrors the Ollama provider's saturation threshold. Duplicated here as a
# module-level fallback so admission tests have a sensible default when the
# caller doesn't pass one through state. The dispatcher should still source
# the live value from the provider so an env-var change propagates without
# editing this file.
OLLAMA_SATURATION_THRESHOLD = int(
    os.environ.get("OLLAMA_SATURATION_THRESHOLD", "8")
)


# ---- Reason strings (emitted on the OTel admission.denied counter) -------

REASON_OLLAMA_SATURATED = "ollama_saturated"
# Emitted when the model-pool scheduler is running but currently has zero
# loaded models. Rare + transient — caller should retry within a few
# seconds while the scheduler tick() promotes the first queue entry.
REASON_OLLAMA_POOL_EMPTY = "ollama_pool_empty"
REASON_CLAUDE_SANITY_SENTINEL = "claude_sanity_sentinel"
# Informational reason for the "dice didn't land Claude AND Ollama was full"
# case. The dispatcher still returns 429 with retry_after sourced from the
# Ollama saturation hint, but logs/metrics tag the deny with this label so
# the dashboard can distinguish "I rolled Ollama and it was full" from
# "I rolled Ollama and it accepted" vs "dice put me on Claude". Today this
# is the same wire-level outcome as REASON_OLLAMA_SATURATED but the label
# lets ops disambiguate at a glance.
REASON_CLAUDE_NOT_SAMPLED = "claude_not_sampled"

# Back-compat reason strings — no longer emitted as live deny reasons under
# the tiered-sampler model, but kept in the module enum so old dashboards
# that pin a Prometheus label value still parse. Safe to drop once every
# downstream panel migrates away.
REASON_CLAUDE_OVERPACE = "claude_overpace"  # deprecated
REASON_CLAUDE_CAP = "claude_daily_cap_reached"  # deprecated
REASON_BOTH = "both"  # deprecated — the dice IS the admission now


def claude_sample_rate(spend_usd: float) -> float:
    """Return today's Claude sample probability given default-lane spend.

    The curve is a step function: ``CLAUDE_SAMPLE_BASE_RATE`` (10%) while
    spend is below the base ($40), then divided by 10 for every additional
    ``CLAUDE_SAMPLE_TIER_WIDTH`` ($20) of spend.

      spend < $40   →  0.10
      $40 ≤ s < $60 →  0.01
      $60 ≤ s < $80 →  0.001
      ...

    Negative spend is treated as 0. The floor is mathematically asymptotic
    — at $1000 the rate is ~1e-50, which is just zero for any practical
    purpose; we don't clamp it because (a) the sanity sentinel kicks in
    long before, and (b) callers should never observe a fully-zero rate
    so they can still tell "really small" from "explicitly disabled".
    """
    s = max(0.0, float(spend_usd))
    base = float(CLAUDE_SAMPLE_TIER_BASE)
    width = float(CLAUDE_SAMPLE_TIER_WIDTH)
    base_rate = float(CLAUDE_SAMPLE_BASE_RATE)
    if s < base:
        return base_rate
    # How many full $20 tiers above the base have we entered?
    # Width must be positive — if an operator zeroes it, fall back to a
    # single tier (preserves the base rate forever rather than DivBy0).
    if width <= 0:
        return base_rate
    tier_index = int((s - base) // width) + 1
    # Each tier divides by 10; cap exponent at a generous bound to keep
    # the result a real float (10**-308 is still > 0 in IEEE-754).
    tier_index = min(tier_index, 300)
    return base_rate * (10.0 ** (-tier_index))


def claude_sample_tier(spend_usd: float) -> int:
    """Integer tier index (0 == base, 1 == first decay step, …).

    Companion to ``claude_sample_rate`` for dashboards that want a discrete
    "which tier are we in" value to plot alongside the continuous rate.
    """
    s = max(0.0, float(spend_usd))
    base = float(CLAUDE_SAMPLE_TIER_BASE)
    width = float(CLAUDE_SAMPLE_TIER_WIDTH)
    if s < base:
        return 0
    if width <= 0:
        return 0
    return int((s - base) // width) + 1


def ollama_admit(state: dict[str, Any]) -> tuple[bool, float, str]:
    """Test whether an Ollama request should be admitted.

    Returns ``(admitted, retry_after_s, reason)``. When admitted, both
    ``retry_after_s`` and ``reason`` are zero-valued — callers should ignore
    them. When denied, ``reason == REASON_OLLAMA_SATURATED`` and
    ``retry_after_s`` is a hint at how long the queue is likely to drain.

    Saturation hint defaults to 1.0 seconds — a coarse but useful baseline
    given that on the .240 daemon NUM_PARALLEL=8 and a typical generation
    takes ~1s wall-clock. The dispatcher can sharpen this later by passing
    a measured p99 latency in ``state["p99_latency_s"]``.
    """
    threshold = int(state.get("saturation_threshold", OLLAMA_SATURATION_THRESHOLD))
    in_flight = int(state.get("in_flight", 0))
    if in_flight < threshold:
        return True, 0.0, ""
    # Crude drain estimate: if a measured p99 is supplied use that, else 1s.
    p99 = state.get("p99_latency_s")
    retry_after = float(p99) if p99 is not None else 1.0
    return False, max(0.1, retry_after), REASON_OLLAMA_SATURATED


def claude_admit_default(state: dict[str, Any]) -> tuple[bool, float, str]:
    """Test whether a default-lane Claude request should be admitted.

    Under the tiered-sampler model, the dice roll IS the admission — by the
    time this function is called the caller has already decided Claude is
    the target. The only thing left to enforce is the sanity sentinel.

    Returns ``(True, 0.0, "")`` in the happy path. When the sentinel trips,
    returns ``(False, retry_after_s, REASON_CLAUDE_SANITY_SENTINEL)`` with
    a long retry hint (60s — give the operator time to investigate).
    """
    sentinel = float(state.get("sentinel_usd", CLAUDE_SANITY_SENTINEL_USD))
    spend = float(state.get("default_spend_usd", 0.0))
    if spend >= sentinel:
        # 60s is a "stop hammering" hint, not an SLA. If we hit this, ops
        # needs to look at the gateway not the retry loop.
        return False, 60.0, REASON_CLAUDE_SANITY_SENTINEL
    return True, 0.0, ""


__all__ = [
    "CLAUDE_SAMPLE_BASE_RATE",
    "CLAUDE_SAMPLE_TIER_BASE",
    "CLAUDE_SAMPLE_TIER_WIDTH",
    "CLAUDE_SANITY_SENTINEL_USD",
    "OLLAMA_SATURATION_THRESHOLD",
    "REASON_BOTH",
    "REASON_CLAUDE_CAP",
    "REASON_CLAUDE_NOT_SAMPLED",
    "REASON_CLAUDE_OVERPACE",
    "REASON_CLAUDE_SANITY_SENTINEL",
    "REASON_OLLAMA_POOL_EMPTY",
    "REASON_OLLAMA_SATURATED",
    "claude_admit_default",
    "claude_sample_rate",
    "claude_sample_tier",
    "ollama_admit",
]
