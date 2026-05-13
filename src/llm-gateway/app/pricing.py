"""LLM cost calculator.

Prices are USD-per-token (already divided down from the published $/MTok
rates). Unknown models cost $0 so a misnamed model doesn't surprise the
caller with a NaN — operators can spot the zero in the dashboard and add the
row here. Keep this table in sync with `docs/PROVIDERS.md`.
"""
from __future__ import annotations

# Anthropic published prices: Haiku $0.25/$1.25 per MTok, Sonnet $3/$15,
# Opus $15/$75 (input/output). Local Ollama models are free.
PRICES: dict[str, dict[str, float]] = {
    # Claude 4.x family (Phase 1 default + the two heavier siblings)
    "claude-haiku-4-5-20251001": {"input": 0.25 / 1_000_000, "output": 1.25 / 1_000_000},
    "claude-sonnet-4-6": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-opus-4-7": {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
    # Local / Ollama — always free.
    "llama3.1:8b": {"input": 0.0, "output": 0.0},
    "llama3.2:3b": {"input": 0.0, "output": 0.0},
    "qwen2.5:7b": {"input": 0.0, "output": 0.0},
    "phi3:mini": {"input": 0.0, "output": 0.0},
}


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
