"""
ObserVIBElity dashboard design tokens — single source of truth.

Imported by rebuild scripts so every curated dashboard uses the same colors,
spacing, units, and helper functions. The narrative rules live in
`design_system.md`; this file is the executable companion.

Pair with `_apply_ai_obs_aesthetic.py` (the final aesthetic pass).
"""

# ----- Color palette ----------------------------------------------------------

# Soft palette — for ranking, mixes, model breakdowns, "AI feel" headlines.
PALETTE = {
    "blue":   "#8AB8FF",
    "purple": "#A78BFA",
    "pink":   "#F472B6",
    "orange": "#FB923C",
    "cyan":   "#67E8F9",
    "mint":   "#86EFAC",
    "rose":   "#FCA5A5",
}

# Status palette — for healthy/unhealthy. Never mix with PALETTE in one panel.
STATUS = {
    "healthy": "#10B981",  # green-500
    "warning": "#F59E0B",  # amber-500
    "danger":  "#EF4444",  # red-500
    "muted":   "#9CA3AF",  # gray-400 — for baselines, secondary labels
    "page_bg": "#0B1020",  # darker than Grafana default; matches the ribbon
}

# Per-model color pins — every chart that splits by model should use these
# (matches `MODEL_COLOR_PINS` in `_apply_ai_obs_aesthetic.py`).
MODEL_COLORS = {
    "claude-opus-4-7":            PALETTE["purple"],
    "claude-opus-4-5-20251015":   "#C084FC",
    "claude-opus-4-5":            "#C084FC",
    "claude-sonnet-4-6":          PALETTE["blue"],
    "claude-haiku-4-5-20251001":  PALETTE["cyan"],
    "claude-haiku-4-5":           PALETTE["cyan"],
    "gemma2:2b":                  PALETTE["mint"],
    "llama3.2:1b":                PALETTE["pink"],
    "llama3.2:latest":            PALETTE["pink"],
    "llama3.1:8b":                PALETTE["rose"],
    "phi3:mini":                  PALETTE["orange"],
    "qwen2.5:7b":                 PALETTE["rose"],
    "qwen3:30b-a3b-instruct-2507-q4_K_M": PALETTE["mint"],
    "tinyllama:1.1b":             "#FCD34D",
    "anthropic":                  PALETTE["pink"],
    "ollama":                     PALETTE["cyan"],
    "loadgen":                    PALETTE["cyan"],
    "live":                       PALETTE["purple"],
    "pass":                       PALETTE["cyan"],
    "fail":                       PALETTE["pink"],
}

# ----- Layout / sizing --------------------------------------------------------

GRID_COLS = 24

# Standard panel sizes (w, h). Use these by name, not raw numbers.
SIZE = {
    "hero":           (12, 8),   # row's dominant stat
    "hero_text":      (8, 8),    # text callout next to a hero
    "hero_double":    (8, 8),    # two heroes side by side
    "kpi":            (6, 4),    # supporting stat
    "kpi_compact":    (4, 4),    # half-kpi
    "state_timeline": (12, 7),   # one row of state timeline
    "chart":          (24, 8),   # full-width timeseries / barchart
    "chart_tall":     (24, 9),   # stacked-by-model bars
    "row_header":     (24, 1),
    "roi_text":       (24, 10),
}

# Standard heights for vertical math in rebuild scripts.
H = {
    "ribbon": 3,
    "row_header": 1,
    "hero": 8,
    "kpi": 4,
    "state_timeline": 7,
    "chart": 8,
    "chart_tall": 9,
    "roi_text": 10,
}

# ----- Units ------------------------------------------------------------------

# Human-relatable unit choices keyed by the metric *intent*, not the raw shape.
UNIT = {
    "currency_total":     "currencyUSD",                # "$905K"
    "currency_per_hour":  "currencyUSD",                # rate × 3600, shown as $/hr
    "currency_per_min":   "currencyUSD",                # rate × 60, shown as $/min
    "currency_per_mtoken": "suffix:$/1M tokens",        # cost-per-token math, scaled
    "calls_per_min":      "suffix: calls/min",          # rate × 60
    "carts_per_hour":     "suffix: carts/hr",
    "tokens_per_min":     "suffix: tokens/min",
    "tokens_per_hour":    "suffix: tokens/hr",
    "percent":            "percent",                    # 0–100
    "ms":                 "ms",
    "hours":              "suffix: hours",
    "carts":              "suffix: carts",
    "errors_per_min":     "suffix: errors/min",
    "none":               "none",
}

DECIMALS = {
    "currency": 0,
    "percent":  1,
    "ms":       0,
    "rate":     2,
    "count":    0,
}

# ----- Threshold helpers ------------------------------------------------------

def status_steps(*, kind="healthy_good"):
    """
    Threshold step list for the status palette.
      kind="healthy_good": low values amber, high values green ("more = healthier")
      kind="healthy_bad":  low values green, high values red    ("more = worse")
    Caller supplies the breakpoints by overriding `.value` on the returned dicts.
    """
    if kind == "healthy_good":
        return [
            {"color": STATUS["danger"],  "value": None},
            {"color": STATUS["warning"], "value": 70},
            {"color": STATUS["healthy"], "value": 95},
        ]
    elif kind == "healthy_bad":
        return [
            {"color": STATUS["healthy"], "value": None},
            {"color": STATUS["warning"], "value": 1},
            {"color": STATUS["danger"],  "value": 50_000},
        ]
    elif kind == "soft_gradient":
        # Use this for bargauges / barcharts where you want the blue→pink→orange
        # gradient. Convert to percentage-mode thresholds when applying.
        return [
            {"color": PALETTE["blue"],   "value": None},
            {"color": PALETTE["purple"], "value": 33},
            {"color": PALETTE["pink"],   "value": 66},
            {"color": PALETTE["orange"], "value": 88},
        ]
    elif kind == "neutral":
        return [{"color": STATUS["muted"], "value": None}]
    else:
        raise ValueError(f"unknown threshold kind: {kind}")


# ----- Datasource refs --------------------------------------------------------

DS = {
    "loki": {"type": "loki", "uid": "${datasource_loki}"},
    "prom": {"type": "prometheus", "uid": "${datasource_prom}"},
}


# ----- Variable templates -----------------------------------------------------

def textbox_var(name, label, default):
    """Build a textbox template variable definition."""
    return {
        "current": {"selected": True, "text": str(default), "value": str(default)},
        "hide": 0,
        "label": label,
        "name": name,
        "options": [{"selected": True, "text": str(default), "value": str(default)}],
        "query": str(default),
        "skipUrlSync": False,
        "type": "textbox",
    }


def datasource_var(name, ds_type, default_value, label):
    return {
        "allowCustomValue": True,
        "current": {"selected": True, "text": default_value, "value": default_value},
        "hide": 0,
        "includeAll": False,
        "label": label,
        "multi": False,
        "name": name,
        "options": [],
        "query": ds_type,
        "refresh": 1,
        "regex": "",
        "skipUrlSync": False,
        "type": "datasource",
    }


STANDARD_VARS = [
    datasource_var("datasource_loki", "loki", "grafanacloud-logs", "Loki datasource"),
    datasource_var("datasource_prom", "prometheus", "grafanacloud-prom", "Prometheus datasource"),
]


# ----- Section headers (rows) -------------------------------------------------

# Canonical row title templates — keep emojis stable across dashboards so
# users recognize the section at a glance.
ROW_TITLE = {
    "business":   "💰 Revenue right now — what the engine is making",
    "missed":     "📉 Missed revenue — what today's downtime actually cost",
    "projected":  "🛑 Cost if the engine stops — what an outage costs the business",
    "journey":    "👥 Customer journey — can shoppers reach checkout?",
    "engine":     "📈 When the engine ran vs. stopped",
    "flow":       "📊 Revenue per 10-minute block — what we made, what we missed",
    "sources":    "🎯 Where the revenue came from",
    "models":     "🤖 AI model economics — who's contributing, who's expensive",
    "action":     "💡 Why this dashboard pays for itself",
    "errors":     "🚨 Errors firing right now",
    "tokens":     "🧠 Token flow — what the LLM gateway is doing",
}
