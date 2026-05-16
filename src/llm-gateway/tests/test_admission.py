"""Tests for the admission-control routing in app.admission + app.main.

Two test surfaces:

* ``app.admission`` pure-function tests — fast, no FastAPI involved.
* ``/v1/complete`` integration tests via FastAPI's TestClient — verify the
  dispatcher wires admission into HTTP-layer behavior (interactive bypass,
  429 on default-lane denial, body shape).

Pydantic + FastAPI must be importable for the integration half. The pure
``app.admission`` tests don't depend on either and run standalone.

Under the tiered-sampler routing model:

  * The default lane rolls a die per request:
    ``P(target=anthropic) == claude_sample_rate(default_spend_today)``.
  * 10% under $40 of spend; cuts by 10x for every additional $20 over $40.
  * No fallback between providers — the dice IS the admission. If the dice
    picks Ollama and Ollama is full, the caller gets 429. If the dice
    picks Claude, Claude is routed unconditionally unless the sanity
    sentinel ($200 default-lane spend) trips.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.admission import (
    CLAUDE_SAMPLE_BASE_RATE,
    CLAUDE_SAMPLE_TIER_BASE,
    CLAUDE_SAMPLE_TIER_WIDTH,
    CLAUDE_SANITY_SENTINEL_USD,
    OLLAMA_SATURATION_THRESHOLD,
    REASON_CLAUDE_NOT_SAMPLED,
    REASON_CLAUDE_SANITY_SENTINEL,
    REASON_OLLAMA_SATURATED,
    claude_admit_default,
    claude_sample_rate,
    claude_sample_tier,
    ollama_admit,
)


# ---- Pure admission-function tests --------------------------------------


def test_ollama_admit_below_threshold_admits():
    """In-flight under the threshold should always admit."""
    admitted, retry, reason = ollama_admit({"in_flight": 0, "saturation_threshold": 8})
    assert admitted is True
    assert retry == 0.0
    assert reason == ""

    admitted, _, _ = ollama_admit({"in_flight": 7, "saturation_threshold": 8})
    assert admitted is True


def test_ollama_admit_at_or_above_threshold_denies():
    """In-flight at/above the threshold should deny with the saturation reason."""
    admitted, retry, reason = ollama_admit(
        {"in_flight": 8, "saturation_threshold": 8}
    )
    assert admitted is False
    assert reason == REASON_OLLAMA_SATURATED
    assert retry >= 0.1  # never advise a sub-100ms wait

    admitted, _, _ = ollama_admit(
        {"in_flight": 99, "saturation_threshold": 8}
    )
    assert admitted is False


def test_ollama_admit_default_threshold_when_unspecified():
    """When the caller omits ``saturation_threshold``, the module default kicks in."""
    admitted, _, _ = ollama_admit({"in_flight": OLLAMA_SATURATION_THRESHOLD - 1})
    assert admitted is True
    admitted, _, _ = ollama_admit({"in_flight": OLLAMA_SATURATION_THRESHOLD})
    assert admitted is False


def test_ollama_admit_honors_p99_hint():
    """A measured p99 should drive retry_after instead of the 1s baseline."""
    admitted, retry, _ = ollama_admit(
        {"in_flight": 8, "saturation_threshold": 8, "p99_latency_s": 2.5}
    )
    assert admitted is False
    assert retry == 2.5


# ---- claude_sample_rate curve ------------------------------------------


def test_claude_sample_rate_base_tier_at_zero_spend():
    """At $0 spend, the rate is the base 10%."""
    assert claude_sample_rate(0.0) == pytest.approx(0.10)


def test_claude_sample_rate_base_tier_just_under_threshold():
    """Just under the $40 base, still 10%."""
    assert claude_sample_rate(39.99) == pytest.approx(0.10)


def test_claude_sample_rate_first_decay_at_40():
    """At exactly $40, drop to 1%."""
    assert claude_sample_rate(40.0) == pytest.approx(0.01)


def test_claude_sample_rate_second_decay_at_60():
    """At exactly $60, drop to 0.1%."""
    assert claude_sample_rate(60.0) == pytest.approx(0.001)


def test_claude_sample_rate_third_decay_at_80():
    """At exactly $80, drop to 0.01%."""
    assert claude_sample_rate(80.0) == pytest.approx(0.0001)


def test_claude_sample_rate_fourth_decay_at_100():
    """At exactly $100, drop to 0.001%."""
    assert claude_sample_rate(100.0) == pytest.approx(0.00001)


def test_claude_sample_rate_fifth_decay_at_120():
    """At exactly $120, drop to 0.0001%."""
    assert claude_sample_rate(120.0) == pytest.approx(0.000001)


def test_claude_sample_rate_mid_tier_holds_constant():
    """The curve is a step function — mid-tier values are constant."""
    # $50 sits inside the $40-$60 tier; rate should match the $40 value.
    assert claude_sample_rate(50.0) == claude_sample_rate(40.0)
    # $70 in the $60-$80 tier.
    assert claude_sample_rate(70.0) == claude_sample_rate(60.0)


def test_claude_sample_rate_negative_treated_as_zero():
    """Negative spend (shouldn't happen, but cost calc has had bugs) → base rate."""
    assert claude_sample_rate(-5.0) == pytest.approx(0.10)


def test_claude_sample_rate_decays_by_factor_of_10_per_tier():
    """Each $20 above the $40 base divides the rate by 10."""
    for tier in range(0, 6):
        spend = 40.0 + tier * 20.0
        expected = 0.10 * (10.0 ** -(tier + 1)) if tier >= 0 else 0.10
        # tier == 0 maps to spend $40 which is the first decay (1%).
        assert claude_sample_rate(spend) == pytest.approx(expected, rel=1e-9)


def test_claude_sample_tier_step_function():
    """Discrete tier index — 0 in the base, increments by 1 each $20."""
    assert claude_sample_tier(0.0) == 0
    assert claude_sample_tier(39.99) == 0
    assert claude_sample_tier(40.0) == 1
    assert claude_sample_tier(50.0) == 1
    assert claude_sample_tier(60.0) == 2
    assert claude_sample_tier(80.0) == 3
    assert claude_sample_tier(100.0) == 4
    assert claude_sample_tier(120.0) == 5


# ---- claude_admit_default (sanity-sentinel only) -----------------------


def test_claude_admit_default_under_sentinel_admits():
    """Anything below the sanity sentinel admits — the dice did the throttling."""
    for spend in (0.0, 10.0, 50.0, 150.0, 199.99):
        admitted, retry, reason = claude_admit_default(
            {"default_spend_usd": spend}
        )
        assert admitted is True, f"failed at spend=${spend}"
        assert retry == 0.0
        assert reason == ""


def test_claude_admit_default_at_sentinel_denies():
    """At the $200 sanity sentinel, deny with claude_sanity_sentinel reason."""
    admitted, retry, reason = claude_admit_default(
        {"default_spend_usd": 200.0}
    )
    assert admitted is False
    assert reason == REASON_CLAUDE_SANITY_SENTINEL
    # 60s "stop hammering" hint — not an SLA.
    assert retry == pytest.approx(60.0)


def test_claude_admit_default_above_sentinel_denies():
    """Past the sentinel, still denied with the sentinel reason."""
    admitted, _, reason = claude_admit_default(
        {"default_spend_usd": 500.0}
    )
    assert admitted is False
    assert reason == REASON_CLAUDE_SANITY_SENTINEL


def test_claude_admit_default_honors_state_sentinel_override():
    """If the dispatcher passes a custom sentinel in state, use it."""
    # Override sentinel to $50 for this call → $100 spend trips it.
    admitted, _, reason = claude_admit_default(
        {"default_spend_usd": 100.0, "sentinel_usd": 50.0}
    )
    assert admitted is False
    assert reason == REASON_CLAUDE_SANITY_SENTINEL


# ---- Module constants ---------------------------------------------------


def test_constants_match_brief():
    """Sanity check: brief says $200 sentinel, $40 tier base, $20 width, 10% base."""
    assert CLAUDE_SANITY_SENTINEL_USD == pytest.approx(200.0)
    assert CLAUDE_SAMPLE_TIER_BASE == pytest.approx(40.0)
    assert CLAUDE_SAMPLE_TIER_WIDTH == pytest.approx(20.0)
    assert CLAUDE_SAMPLE_BASE_RATE == pytest.approx(0.10)
    assert OLLAMA_SATURATION_THRESHOLD == 8


# ---- FastAPI integration tests for /v1/complete -------------------------

# These tests pull in FastAPI's TestClient + the gateway app. We patch out
# the providers so no real HTTP / Ollama / Anthropic call ever fires.


@pytest.fixture()
def integration_setup():
    """Spin up the gateway with two fake providers and reset the spend ledger."""
    pytest.importorskip("fastapi")
    pytest.importorskip("pydantic")

    from fastapi.testclient import TestClient

    from app import main
    from app.providers.base import CompleteResponse, Provider

    class _FakeAnthropic(Provider):
        name = "anthropic"
        model = "claude-haiku-4-5-fake"

        async def complete(self, req):  # type: ignore[override]
            return CompleteResponse(
                content="claude-says-hi",
                tool_calls=[],
                finish_reason="stop",
                usage={"input_tokens": 10, "output_tokens": 5},
                provider=self.name,
                model=self.model,
            )

        async def healthy(self):  # type: ignore[override]
            return True

    class _FakeOllama(Provider):
        name = "ollama"
        model = "llama3.1:8b-fake"

        def __init__(self, config=None):
            super().__init__(config)
            self._in_flight = 0

        @property
        def in_flight(self):
            return self._in_flight

        async def complete(self, req):  # type: ignore[override]
            return CompleteResponse(
                content="ollama-says-hi",
                tool_calls=[],
                finish_reason="stop",
                usage={"input_tokens": 10, "output_tokens": 5},
                provider=self.name,
                model=self.model,
            )

        async def healthy(self):  # type: ignore[override]
            return True

    fake_ollama = _FakeOllama()
    fake_anthropic = _FakeAnthropic()

    # Reset the per-lane spend ledger so tests don't see state from earlier
    # tests in the same pytest session.
    main._claude_default_spend_today = 0.0
    main._claude_interactive_spend_today = 0.0
    main._claude_budget_day_utc = ""

    with TestClient(main.app) as client:
        client.app.state.providers = {
            "ollama": fake_ollama,
            "anthropic": fake_anthropic,
        }
        client.app.state.default_provider = "ollama"
        yield client, fake_ollama, fake_anthropic, main


def test_interactive_lane_bypasses_admission_and_uses_claude(integration_setup):
    """``traffic_origin == "interactive"`` MUST always land on Claude.

    Saturate Ollama AND park default-lane spend past the sanity sentinel so
    default-lane routing would 429. The interactive request should still
    succeed because it bypasses admission entirely.
    """
    client, fake_ollama, _, main = integration_setup
    fake_ollama._in_flight = 99  # well above threshold
    main._claude_default_spend_today = 1_000.0  # past sentinel

    payload = {
        "specialist": "nc-chatbot",
        "messages": [{"role": "user", "content": "hi"}],
        "ai_o11y": {"usecase": "demo", "traffic_origin": "interactive"},
    }
    r = client.post("/v1/complete", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "anthropic"
    assert body["content"] == "claude-says-hi"


def test_interactive_lane_header_form(integration_setup):
    """``X-Traffic-Origin: interactive`` header should also force the lane."""
    client, fake_ollama, _, main = integration_setup
    fake_ollama._in_flight = 99
    main._claude_default_spend_today = 1_000.0

    r = client.post(
        "/v1/complete",
        json={
            "specialist": "nc-chatbot",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"X-Traffic-Origin": "interactive"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "anthropic"


def test_interactive_spend_does_not_increment_default_ledger(integration_setup):
    """Interactive Claude calls go on the interactive ledger, not default."""
    client, _, _, main = integration_setup
    before_default = main._claude_default_spend_today

    payload = {
        "specialist": "nc-chatbot",
        "messages": [{"role": "user", "content": "hi"}],
        "ai_o11y": {"traffic_origin": "interactive"},
    }
    r = client.post("/v1/complete", json=payload)
    assert r.status_code == 200

    # Default ledger unchanged; interactive ledger may or may not have moved
    # depending on whether the fake Claude model has a pricing entry —
    # what matters is the default side stays untouched.
    assert main._claude_default_spend_today == before_default


def test_default_lane_429_when_ollama_full_and_dice_landed_ollama(integration_setup):
    """Dice landed on Ollama + Ollama full → 429, NO fallback to Claude."""
    client, fake_ollama, _, _ = integration_setup
    fake_ollama._in_flight = 99  # saturated

    # Force the dice to pick Ollama (high random value → P(claude) is 10%
    # at $0 spend, so any value >= 0.10 picks Ollama).
    with patch("app.main.random.random", return_value=0.9):
        r = client.post(
            "/v1/complete",
            json={
                "specialist": "loadgen-worker",
                "messages": [{"role": "user", "content": "hi"}],
                "ai_o11y": {"traffic_origin": "continuous"},
            },
        )
    assert r.status_code == 429, r.text
    body = r.json()
    # Body shape contract — the dashboard agent + client retry loops parse
    # these fields; new fields (sample_rate/tier) added under tiered model.
    assert set(body.keys()) >= {
        "reason",
        "retry_after_s",
        "primary_provider_tried",
        "secondary_provider_tried",
    }
    assert body["primary_provider_tried"] == "ollama"
    # No fallback — secondary is unused under the tiered-sampler model.
    assert body["secondary_provider_tried"] == ""
    assert body["retry_after_s"] >= 0.1
    # Retry-After header is integer seconds per RFC.
    assert "retry-after" in {k.lower() for k in r.headers.keys()}
    assert int(r.headers["retry-after"]) >= 1
    # Reason should tag this as "the dice didn't pick Claude" (informational
    # — wire behavior matches ollama_saturated either way).
    assert body["reason"] == REASON_CLAUDE_NOT_SAMPLED


def test_default_lane_routes_to_ollama_when_dice_landed_ollama(integration_setup):
    """Dice picks Ollama, Ollama has capacity → routed there cleanly."""
    client, _, _, _ = integration_setup
    with patch("app.main.random.random", return_value=0.9):
        r = client.post(
            "/v1/complete",
            json={
                "specialist": "loadgen-worker",
                "messages": [{"role": "user", "content": "hi"}],
                "ai_o11y": {"traffic_origin": "continuous"},
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "ollama"


def test_default_lane_routes_to_claude_when_dice_landed_claude(integration_setup):
    """At $0 spend, P(claude)=0.10 → random.random()=0.05 lands Claude."""
    client, _, _, _ = integration_setup
    # 0.05 < 0.10 → dice picks Claude.
    with patch("app.main.random.random", return_value=0.05):
        r = client.post(
            "/v1/complete",
            json={
                "specialist": "loadgen-worker",
                "messages": [{"role": "user", "content": "hi"}],
                "ai_o11y": {"traffic_origin": "continuous"},
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "anthropic"


def test_default_lane_routes_to_claude_even_when_ollama_full(integration_setup):
    """Dice picks Claude + Ollama saturated → still routed to Claude.

    The dice IS the admission; Ollama saturation is irrelevant once the
    sampler has chosen Claude.
    """
    client, fake_ollama, _, _ = integration_setup
    fake_ollama._in_flight = 99  # saturated
    with patch("app.main.random.random", return_value=0.05):  # picks Claude
        r = client.post(
            "/v1/complete",
            json={
                "specialist": "loadgen-worker",
                "messages": [{"role": "user", "content": "hi"}],
                "ai_o11y": {"traffic_origin": "continuous"},
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "anthropic"


def test_default_lane_sanity_sentinel_denies_claude(integration_setup):
    """Spend ≥ $200 → all Claude requests 429 with sanity_sentinel reason."""
    client, _, _, main = integration_setup
    main._claude_default_spend_today = 200.0  # at sentinel

    # Force dice to pick Claude despite the (vanishingly small) sample
    # rate at this spend tier — the sentinel must override.
    with patch("app.main.random.random", return_value=0.0):
        r = client.post(
            "/v1/complete",
            json={
                "specialist": "loadgen-worker",
                "messages": [{"role": "user", "content": "hi"}],
                "ai_o11y": {"traffic_origin": "continuous"},
            },
        )
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["reason"] == REASON_CLAUDE_SANITY_SENTINEL
    assert body["primary_provider_tried"] == "anthropic"
    assert body["retry_after_s"] >= 1.0


def test_default_lane_sample_rate_decays_with_spend(integration_setup):
    """At $50 default-lane spend, the body's sample_rate should report 1%."""
    client, fake_ollama, _, main = integration_setup
    fake_ollama._in_flight = 99  # force a 429 so we get the body to inspect
    main._claude_default_spend_today = 50.0  # tier 1 → 1% Claude

    # High random → dice picks Ollama → 429 with the sample-rate in the body.
    with patch("app.main.random.random", return_value=0.9):
        r = client.post(
            "/v1/complete",
            json={
                "specialist": "loadgen-worker",
                "messages": [{"role": "user", "content": "hi"}],
                "ai_o11y": {"traffic_origin": "continuous"},
            },
        )
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["sample_rate"] == pytest.approx(0.01)
    assert body["sample_tier"] == 1


def test_dice_distribution_at_zero_spend_is_10_percent_claude(integration_setup):
    """At $0 spend, ~10% of dice rolls should land Claude (1000-bucket sweep)."""
    pytest.importorskip("fastapi")
    from app.main import _sample_target

    # Use a deterministic sweep instead of statistical luck — every 0.x
    # value between 0 and 1 in 1k buckets gets sampled exactly once, so
    # the count is mathematically determined by the threshold.
    counts = {"ollama": 0, "anthropic": 0}
    seq = iter([i / 1000.0 for i in range(1000)])
    with patch("app.main.random.random", side_effect=lambda: next(seq)):
        for _ in range(1000):
            counts[_sample_target()] += 1

    # P(claude) == 0.10 at $0 spend → 100 of the 1000 buckets land Claude
    # (every value < 0.10, i.e. 0..99).
    assert counts["anthropic"] == 100
    assert counts["ollama"] == 900


def test_dice_distribution_at_50_dollar_spend_is_1_percent_claude(integration_setup):
    """At $50 default-lane spend (tier 1), ~1% of dice should land Claude."""
    pytest.importorskip("fastapi")
    from app import main
    from app.main import _sample_target

    main._claude_default_spend_today = 50.0
    counts = {"ollama": 0, "anthropic": 0}
    seq = iter([i / 1000.0 for i in range(1000)])
    with patch("app.main.random.random", side_effect=lambda: next(seq)):
        for _ in range(1000):
            counts[_sample_target()] += 1

    # P(claude) == 0.01 at $50 spend → 10 of the 1000 buckets land Claude
    # (every value < 0.01).
    assert counts["anthropic"] == 10
    assert counts["ollama"] == 990
