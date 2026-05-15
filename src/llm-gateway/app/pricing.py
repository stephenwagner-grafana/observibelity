"""LLM cost calculator.

Prices are USD-per-token (already divided down from the published $/MTok
rates). Unknown models cost $0 so a misnamed model doesn't surprise the
caller with a NaN — operators can spot the zero in the dashboard and add the
row here. Keep this table in sync with `docs/PROVIDERS.md`.

The chart's ConfigMap (`llm-gateway-config.pricing.json`) is mounted at
``/etc/llm-gateway/pricing.json`` and loaded at startup via
``load_pricing_overrides`` — that's how operators tune prices without
shipping a new image.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Anthropic published per-MTok rates: Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15,
# Opus 4.7 $15/$75.
#
# Ollama pricing is the honest GPU energy + amortization estimate for a
# desktop RTX 5090 host on a US grid:
#
#   per_active_hour = (GPU_WATTS / 1000) * KWH_USD          # energy
#                   + GPU_PURCHASE_USD / (LIFETIME_YR * 24 * 365)  # amortization
#
#   per_token = per_active_hour / (tok_per_sec * 3600)
#
# Defaults assumed below: 575 W TDP, $0.16/kWh (US average), $2000 GPU over
# 5 years -> ~$0.092/hr energy + ~$0.046/hr amortization = $0.138 per active
# hour of inference. Per-token cost then scales by each model's throughput.
# These can be tuned per deployment via the chart's
# llm-gateway-config.pricing.json ConfigMap.
PRICES: dict[str, dict[str, float]] = {
    # Claude 4.x family — Anthropic published pricing (verify at console.anthropic.com/settings/billing)
    "claude-haiku-4-5-20251001": {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
    "claude-sonnet-4-6": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-opus-4-7": {"input": 15.00 / 1_000_000, "output": 75.00 / 1_000_000},
    # Ollama on RTX 5090, US electricity. Input == output (GPU work is the
    # same per token processed regardless of role). Implied throughputs:
    # tinyllama 600 tok/s, llama3.2:1b 500, gemma2:2b 250, phi3 200,
    # 7B-class ~80, 8B-class ~70, 30B MoE q4 ~60.
    "smollm2:135m":   {"input": 0.02 / 1_000_000, "output": 0.02 / 1_000_000},
    "qwen2.5:0.5b":   {"input": 0.04 / 1_000_000, "output": 0.04 / 1_000_000},
    "tinyllama:1.1b": {"input": 0.06 / 1_000_000, "output": 0.06 / 1_000_000},
    "llama3.2:1b":    {"input": 0.08 / 1_000_000, "output": 0.08 / 1_000_000},
    "llama3.2:latest":{"input": 0.08 / 1_000_000, "output": 0.08 / 1_000_000},
    "gemma2:2b":      {"input": 0.15 / 1_000_000, "output": 0.15 / 1_000_000},
    "phi3:mini":      {"input": 0.19 / 1_000_000, "output": 0.19 / 1_000_000},
    "qwen3:4b":       {"input": 0.25 / 1_000_000, "output": 0.25 / 1_000_000},
    "qwen2.5:7b":     {"input": 0.48 / 1_000_000, "output": 0.48 / 1_000_000},
    "mistral:7b-instruct": {"input": 0.48 / 1_000_000, "output": 0.48 / 1_000_000},
    "llama3.1:8b":    {"input": 0.55 / 1_000_000, "output": 0.55 / 1_000_000},
    "qwen3:30b-a3b-instruct-2507-q4_K_M": {"input": 0.64 / 1_000_000, "output": 0.64 / 1_000_000},
}


def load_pricing_overrides(data: dict[str, Any] | None) -> None:
    """Merge a chart-supplied pricing.json into the module-level PRICES table.

    Accepts either the per-token shape (``{"input": 1e-6, ...}``) or the
    per-million-USD shape used by the chart's ConfigMap
    (``{"input_per_million_usd": 1.0, ...}``). Unknown shapes are skipped with
    a warning so a malformed entry never breaks the gateway.
    """
    if not data:
        return
    for model, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if "input" in entry and "output" in entry:
            try:
                PRICES[model] = {
                    "input": float(entry["input"]),
                    "output": float(entry["output"]),
                }
            except (TypeError, ValueError) as exc:
                log.warning("bad pricing override for %s: %s", model, exc)
            continue
        if "input_per_million_usd" in entry or "output_per_million_usd" in entry:
            try:
                PRICES[model] = {
                    "input": float(entry.get("input_per_million_usd", 0.0))
                    / 1_000_000,
                    "output": float(entry.get("output_per_million_usd", 0.0))
                    / 1_000_000,
                }
            except (TypeError, ValueError) as exc:
                log.warning("bad pricing override for %s: %s", model, exc)
            continue
        log.warning("skipping pricing entry with unknown shape: %s", model)


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> dict[str, float]:
    """Return the per-call cost breakdown in USD.

    Unknown models are priced at $0 so a typo or new model doesn't crash the
    request path — it just shows up as "free" in dashboards until someone
    notices and adds the row.
    """
    p = PRICES.get(model, {"input": 0.0, "output": 0.0})
    input_usd = float(input_tokens) * p["input"]
    output_usd = float(output_tokens) * p["output"]
    return {
        "input_usd": input_usd,
        "output_usd": output_usd,
        "total_usd": input_usd + output_usd,
    }
