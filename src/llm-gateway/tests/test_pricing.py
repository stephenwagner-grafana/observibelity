"""Unit tests for app.pricing.compute_cost."""
from __future__ import annotations

import pytest

from app.pricing import PRICES, compute_cost


def test_haiku_cost_matches_published_rate():
    cost = compute_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    # Published rates: $0.25 input / $1.25 output per MTok.
    assert cost["input_usd"] == pytest.approx(0.25)
    assert cost["output_usd"] == pytest.approx(1.25)
    assert cost["total_usd"] == pytest.approx(1.50)


def test_sonnet_cost_matches_published_rate():
    cost = compute_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    # Published rates: $3 input / $15 output per MTok.
    assert cost["input_usd"] == pytest.approx(3.0)
    assert cost["output_usd"] == pytest.approx(15.0)
    assert cost["total_usd"] == pytest.approx(18.0)


def test_unknown_model_is_free():
    cost = compute_cost("totally-fake-model:v0", 1_000_000, 1_000_000)
    assert cost == {"input_usd": 0.0, "output_usd": 0.0, "total_usd": 0.0}


def test_zero_tokens_zero_cost():
    cost = compute_cost("claude-haiku-4-5-20251001", 0, 0)
    assert cost["total_usd"] == 0.0


def test_ollama_local_model_is_free():
    cost = compute_cost("llama3.1:8b", 50_000, 50_000)
    assert cost["total_usd"] == 0.0


def test_prices_table_well_formed():
    for model, p in PRICES.items():
        assert {"input", "output"} <= set(p.keys()), f"{model} missing keys"
        assert p["input"] >= 0 and p["output"] >= 0, f"{model} has negative price"
