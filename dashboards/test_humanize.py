"""
Golden tests for the humanize-metric skill.

Each test pins one canonical (input → recommendation) pairing. When the
table or logic changes, these tests catch regressions; when the spec in
HUMANIZE_METRIC.md grows, add a matching test here.

Run:  python3 -m pytest dashboards/test_humanize.py -v
"""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from humanize import humanize


# ---------------------------------------------------------------------------
# Mode 1 — SI / unit-family scaling
# ---------------------------------------------------------------------------

def test_ms_scales_to_seconds():
    rec = humanize("response_time_ms", 1500.0, "SRE", unit_family="time")
    assert rec.mode == "scale"
    assert rec.unit == "h" or rec.unit in {"s", "m", "h"}
    assert "1500" not in rec.display_value  # value got scaled
    assert float(rec.display_value) < 100


def test_bytes_scales_to_GB():
    rec = humanize("payload_bytes", 1.2e9, "SRE", unit_family="bytes")
    assert rec.mode == "scale"
    assert rec.unit == "gbytes"
    assert rec.display_value == "1.1"          # 1.2e9 / 1024^3 ≈ 1.117


def test_glanceable_value_stays_convention():
    # 340 ms is already glanceable as ms; mode 1 walks the ladder but
    # the chosen rung lands the same. Acceptable to be either convention
    # or scale — but it must NOT rebase or analogize.
    rec = humanize("latency_ms", 340.0, "SRE", unit_family="time")
    assert rec.mode in {"convention", "scale"}


# ---------------------------------------------------------------------------
# Mode 2a — Population rebasing (the canonical ATC case)
# ---------------------------------------------------------------------------

def test_atc_rebases_to_per_100_customers():
    # 0.03 ATCs/hour = 8.3e-6 ATCs/sec. CFO audience, customer_visits_total
    # available → should rebase to "per 100 customers", NOT to per-day or
    # per-month.
    per_sec = 0.03 / 3600
    rec = humanize(
        "add_to_cart_total",
        per_sec,
        audience="CFO",
        is_rate=True,
        available_series=("customer_visits_total",),
    )
    assert rec.mode == "rebase", f"expected rebase, got {rec.mode}: {rec.notes}"
    assert "100 customers" in rec.custom_unit
    assert "customer_visits_total" in rec.prom_fragment
    assert "* 100" in rec.prom_fragment


def test_error_rate_rebases_per_10k_requests():
    # 0.0001 errors/sec, SRE audience, http_requests_total available
    rec = humanize(
        "http_5xx_total",
        0.0001,
        audience="SRE",
        is_rate=True,
        available_series=("http_requests_total",),
    )
    assert rec.mode == "rebase"
    assert "10K requests" in rec.custom_unit
    assert "http_requests_total" in rec.prom_fragment


# ---------------------------------------------------------------------------
# Mode 2b — Time rebasing (when no population denominator matches)
# ---------------------------------------------------------------------------

def test_spend_rate_rebases_to_month():
    # 5.33e-8 USD/sec, CFO. No population series available → falls through
    # to time denominators. Month projection: 5.33e-8 * 2,592,000 ≈ 0.138.
    # That's still <1, so day (=0.0046) is also <1, so the picker should
    # keep walking… but our list only has month and day in CFO. Both fail
    # the 1-999 test. So this should NOT rebase via time — fall through
    # to mode 3 or convention.
    #
    # Actually a more honest test: pick a value where time-rebase clearly
    # lands. 1e-5 USD/sec * 86400 = 0.864/day (no), * 2592000 = 25.9/month
    # (yes).
    rec = humanize(
        "gen_ai_cost_USD_total",
        1e-5,
        audience="CFO",
        is_rate=True,
        unit_family="currency_usd",
        available_series=(),     # no population denominators available
    )
    assert rec.mode == "rebase"
    assert "/month" in rec.custom_unit or "/day" in rec.custom_unit
    assert rec.unit == "currencyUSD"


# ---------------------------------------------------------------------------
# Mode 3 — Magnitude-fit analogy
# ---------------------------------------------------------------------------

def test_outage_cost_attaches_house_analogy():
    # $1.4M total — analogy domain "spend", anchor at $1M = "a small house".
    rec = humanize(
        "outage_cost_usd",
        1_400_000.0,
        audience="CFO",
        unit_family="currency_usd",
        domain="spend",
    )
    assert rec.mode == "analogy"
    assert rec.analogy is not None
    assert "house" in rec.analogy


def test_ai_throughput_analogy_pages_per_dollar():
    # tokens/$ = 70,000 → "≈ 100 pages per dollar" (anchor at 70,000).
    rec = humanize(
        "tokens_per_usd",
        70_000.0,
        audience="Mixed",
        unit_family="count",
        domain="ai_throughput",
    )
    assert rec.mode == "analogy"
    assert "pages per dollar" in rec.analogy


# ---------------------------------------------------------------------------
# Recommendation shape — every recommendation has the fields the
# grafana-builder skill expects.
# ---------------------------------------------------------------------------

def test_recommendation_has_all_panel_fields():
    rec = humanize(
        "add_to_cart_total",
        0.03 / 3600,
        audience="CFO",
        is_rate=True,
        available_series=("customer_visits_total",),
    )
    d = rec.as_dict()
    for required in ("mode", "display_value", "unit", "custom_unit",
                     "decimals", "axis_label", "description",
                     "prom_fragment", "notes"):
        assert required in d, f"missing field: {required}"


# ---------------------------------------------------------------------------
# Parity — the data table entries the spec calls out must exist.
# ---------------------------------------------------------------------------

def test_audience_profiles_exist():
    from _humanize_table import AUDIENCE_DENOMINATORS
    for required in ("CFO", "SRE", "AI", "Customer", "Mixed"):
        assert required in AUDIENCE_DENOMINATORS, f"missing audience: {required}"


def test_analogy_anchors_for_canonical_magnitudes():
    from _humanize_table import pick_analogy
    # spec's worked examples in HUMANIZE_METRIC.md §7
    assert pick_analogy("spend", 1_000_000) is not None
    assert pick_analogy("time", 1e-3) is not None
    assert pick_analogy("ai_throughput", 70_000) is not None


def test_analogy_returns_none_when_far_off():
    from _humanize_table import pick_analogy
    # nothing in the table should match a wildly off magnitude
    assert pick_analogy("spend", 1e-15) is None
