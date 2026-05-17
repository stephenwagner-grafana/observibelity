"""
Data tables for the humanize-metric skill.

The canonical narrative is dashboards/skills/HUMANIZE_METRIC.md. This file
mirrors its tables in a form Python can index. Tests in test_humanize.py
enforce parity on a few canonical entries — if you add a row to one side,
add it to the other.

Three exported names:

  UNIT_FAMILIES           — SI-style ladders for mechanical mode-1 scaling
  AUDIENCE_DENOMINATORS   — preferred denominators for mode-2 rebasing
  ANALOGIES               — magnitude × domain → tactile phrase for mode 3
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Mode 1 — Unit-family ladders
# ---------------------------------------------------------------------------
#
# Each ladder is ordered low → high. The picker walks until the scaled value
# lands in [1, 999], preferring the LOWEST entry that lands it (i.e. don't
# show "0.5 GB" when "500 MB" works).
#
# Each rung: (multiplier_from_base, grafana_unit, custom_suffix, decimals)

UNIT_FAMILIES = {
    # base unit: second
    "time": [
        (1e-9,  "ns",          "",          0),
        (1e-6,  "µs",          "",          0),
        (1e-3,  "ms",          "",          0),
        (1.0,   "s",           "",          1),
        (60.0,  "m",           "",          1),
        (3600.0,"h",           "",          1),
        (86400.0,"d",          "",          1),
    ],

    # base unit: byte
    "bytes": [
        (1.0,         "bytes",  "",   0),
        (1024.0,      "deckbytes", "", 0),   # Grafana "KiB"
        (1024.0**2,   "mbytes", "",   1),
        (1024.0**3,   "gbytes", "",   1),
        (1024.0**4,   "tbytes", "",   1),
        (1024.0**5,   "pbytes", "",   1),
    ],

    # base unit: USD
    "currency_usd": [
        (1.0,   "currencyUSD", "",   2),    # $1
        (1e3,   "currencyUSD", "",   1),    # $K (Grafana auto-K)
        (1e6,   "currencyUSD", "",   1),    # $M
        (1e9,   "currencyUSD", "",   1),    # $B
    ],

    # base unit: watt
    "power": [
        (1.0,   "watt",       "",    1),
        (1e3,   "kwatt",      "",    1),
        (1e6,   "mwatt",      "",    1),
        (1e9,   "gwatt",      "",    2),
    ],

    # base unit: dimensionless count (use `short` for auto-K/M/B)
    "count": [
        (1.0,   "short",      "",    0),
        (1e3,   "short",      "",    1),
        (1e6,   "short",      "",    1),
        (1e9,   "short",      "",    2),
    ],

    # base unit: tokens (counts but with explicit suffix so non-AI viewers know)
    "tokens": [
        (1.0,         "short", " tokens", 0),
        (1e3,         "short", " tokens", 1),
        (1e6,         "short", " tokens", 1),
        (1e9,         "short", " tokens", 2),
    ],

    # base unit: hertz / per-second rate — fall through to TIME_REBASE_LADDER
    # when the rate is small. See AUDIENCE_DENOMINATORS for mode 2.

    # base unit: 0-1 ratio (percentunit) → percent (0-100)
    "ratio": [
        (1.0,   "percentunit", "",    2),   # 0-1
        (100.0, "percent",     "",    1),   # 0-100
    ],
}


# ---------------------------------------------------------------------------
# Mode 2 — Audience-keyed natural denominators
# ---------------------------------------------------------------------------
#
# A denominator entry says: "if `metric_name` (or a stand-in series) exists
# in your dataset, you may rebase against it. The result is one numerator
# unit per N of these."
#
# `target_basis` is the multiplier so the numerator lands in 1–999 (e.g.
# "* 100" → "per 100 customers"; "* 10000" → "per 10K requests").

@dataclass(frozen=True)
class Denominator:
    name: str                 # the human label, e.g. "customers"
    metric_candidates: tuple  # PromQL series names that could supply it
    target_basis: int         # the multiplier (100, 1000, 10000, 1_000_000)
    short_label: str          # "100 customers", "10K requests"
    description_phrase: str   # "Of every 100 customers who visit, …"


AUDIENCE_DENOMINATORS = {
    "CFO": [
        Denominator("customers",     ("customer_visits_total", "neoncart_visits_total",
                                      "nc_session_total"),                100,
                    "100 customers",   "Of every 100 customers who visit"),
        Denominator("conversations", ("conversation_started_total",
                                      "gen_ai_client_operation_duration_seconds_count"), 100,
                    "100 conversations", "In every 100 conversations"),
        Denominator("orders",        ("order_total", "checkout_complete_total"),         100,
                    "100 orders",      "Per 100 completed orders"),
        Denominator("sessions",      ("session_total", "nc_session_total"),              100,
                    "100 sessions",    "In every 100 sessions"),
        Denominator("month",         (),                                              2592000,
                    "month",           "At the current rate, every month"),
        Denominator("day",           (),                                                86400,
                    "day",             "At the current rate, every day"),
    ],

    "SRE": [
        Denominator("requests",      ("http_requests_total",
                                      "gen_ai_client_operation_duration_seconds_count"), 10000,
                    "10K requests",    "Per 10,000 requests"),
        Denominator("errors",        ("http_5xx_total", "errors_total"),                 100,
                    "100 errors",      "Of every 100 errors"),
        Denominator("deployments",   ("argo_app_sync_total",),                           10,
                    "10 deployments",  "Per 10 deployments"),
        Denominator("hour",          (),                                                 3600,
                    "hour",            "Per hour at current rate"),
        Denominator("minute",        (),                                                  60,
                    "minute",          "Per minute at current rate"),
    ],

    "AI": [
        Denominator("1M tokens",     ("gen_ai_client_token_usage_total",),          1000000,
                    "1M tokens",       "Per million tokens generated"),
        Denominator("model_calls",   ("gen_ai_client_operation_duration_seconds_count",), 1000,
                    "1K model calls",  "Per 1,000 model calls"),
        Denominator("evaluations",   ("sigil_eval_executions_total",),                  100,
                    "100 evals",       "Per 100 evaluations"),
        Denominator("conversation",  ("conversation_started_total",),                   100,
                    "100 conversations","Per 100 conversations"),
    ],

    "Customer": [
        Denominator("users",         ("active_users_total",),                          1000,
                    "1K users",        "Per 1,000 users"),
        Denominator("page_views",    ("page_views_total",),                           10000,
                    "10K page views",  "Per 10,000 page views"),
        Denominator("sessions",      ("session_total",),                                100,
                    "100 sessions",    "In every 100 sessions"),
    ],

    # For mixed/demo audience: try CFO denominators first, fall back to AI,
    # then SRE. Builds the leaderboard order at lookup time.
    "Mixed": "CFO,AI,SRE",
}


# ---------------------------------------------------------------------------
# Mode 3 — Analogy library
# ---------------------------------------------------------------------------
#
# Lookups are by domain + numeric magnitude. The picker chooses the entry
# whose magnitude is closest (within ~3× either direction) to the input
# value. If nothing fits within tolerance, returns None — DO NOT invent.

@dataclass(frozen=True)
class Analogy:
    domain: str          # "spend", "time", "bytes", "tokens", "power", "ai_throughput"
    magnitude: float     # the canonical value this analogy lands at
    phrase: str          # the tactile reference, embedded in panel description


ANALOGIES = (
    # --- Spend ---
    Analogy("spend", 1.0,         "a coffee"),
    Analogy("spend", 10.0,        "a fast-food meal"),
    Analogy("spend", 100.0,       "a tank of gas"),
    Analogy("spend", 1_000.0,     "a budget laptop"),
    Analogy("spend", 10_000.0,    "a used car"),
    Analogy("spend", 100_000.0,   "a starter-home down payment"),
    Analogy("spend", 1_000_000.0, "a small house"),
    Analogy("spend", 10_000_000.0,"a Boeing 737"),

    # --- Time ---
    Analogy("time",  1e-3,  "the blink of an eye"),
    Analogy("time",  1.0,   "a heartbeat"),
    Analogy("time",  60.0,  "reading a tweet"),
    Analogy("time",  3600.0,"a sitcom episode"),
    Analogy("time",  86400.0,"a full workday"),

    # --- Bytes ---
    Analogy("bytes", 1024.0,         "a paragraph of text"),
    Analogy("bytes", 1024.0**2,      "a photo"),
    Analogy("bytes", 1024.0**3,      "an HD movie"),
    Analogy("bytes", 1024.0**4,      "250,000 photos"),
    Analogy("bytes", 1024.0**5,      "a film studio's archive"),

    # --- Tokens (raw, for AI literacy panels) ---
    Analogy("tokens", 100.0,        "a tweet's worth"),
    Analogy("tokens", 1_000.0,      "one printed page"),
    Analogy("tokens", 100_000.0,    "a short novel"),
    Analogy("tokens", 1_000_000.0,  "ten novels"),
    Analogy("tokens", 10_000_000.0, "a small library"),

    # --- Power ---
    Analogy("power", 1.0,    "an LED bulb"),
    Analogy("power", 1e3,    "a microwave at full blast"),
    Analogy("power", 1e6,    "a thousand homes"),
    Analogy("power", 1e9,    "a nuclear reactor"),

    # --- AI throughput: tokens per dollar ---
    # We index by tokens/$, divide by ~700 (output tokens per printed page),
    # so phrases say "N pages of text per $1".
    Analogy("ai_throughput", 700.0,        "≈ 1 page of text per dollar"),
    Analogy("ai_throughput", 7_000.0,      "≈ 10 pages per dollar"),
    Analogy("ai_throughput", 70_000.0,     "≈ 100 pages per dollar"),
    Analogy("ai_throughput", 700_000.0,    "≈ 1,000 pages — a novel — per dollar"),
    Analogy("ai_throughput", 7_000_000.0,  "≈ 10,000 pages per dollar"),
    Analogy("ai_throughput", 70_000_000.0, "≈ a small bookshelf per dollar"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pick_ladder_rung(family: str, value: float):
    """Return the rung (multiplier, unit, suffix, decimals) that lands `value`
    in [1, 999]. Walks low→high; first acceptable rung wins. Falls back to
    the highest rung if nothing fits."""
    rungs = UNIT_FAMILIES.get(family)
    if not rungs:
        return None
    last = rungs[0]
    for mult, unit, suffix, decimals in rungs:
        scaled = value / mult
        if 1.0 <= abs(scaled) < 1000.0:
            return (mult, unit, suffix, decimals)
        last = (mult, unit, suffix, decimals)
    return last


def pick_denominators(audience: str):
    """Return the ordered list of Denominator objects for an audience.
    Resolves the 'Mixed' string-chain to a flat list."""
    profile = AUDIENCE_DENOMINATORS.get(audience)
    if profile is None:
        return []
    if isinstance(profile, str):
        out = []
        for sub in profile.split(","):
            out.extend(AUDIENCE_DENOMINATORS.get(sub.strip(), []))
        return out
    return list(profile)


def pick_analogy(domain: str, value: float, tolerance: float = 3.0):
    """Return the closest Analogy for (domain, value) within `tolerance`×.
    If nothing fits, returns None — DO NOT invent."""
    if value <= 0:
        return None
    best = None
    best_ratio = float("inf")
    for a in ANALOGIES:
        if a.domain != domain:
            continue
        ratio = max(value / a.magnitude, a.magnitude / value)
        if ratio < best_ratio and ratio <= tolerance:
            best = a
            best_ratio = ratio
    return best
