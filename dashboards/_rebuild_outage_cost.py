#!/usr/bin/env python3
"""
Rebuild ai-obs-outage-cost.json with a business/finops-friendly story arc.

Story:
  1. Live revenue pulse (top sparkline)
  2. "Revenue right now" hero row — what we make per hour
  3. "Cost if it goes down" hero row — projected outage cost
  4. "When the engine ran vs stopped" — k3s + k6 state timelines
  5. "Revenue flow over time" — $/hour timeseries with pod-restart annotations
  6. "Where it comes from" — revenue mix by model + top products
  7. "ROI math" — text panel translating annual run rate into observability ROI
"""
import json
from pathlib import Path

DASH = Path(__file__).parent / "ai-obs-outage-cost.json"
data = json.loads(DASH.read_text())

LOKI_DS = {"type": "loki", "uid": "${datasource_loki}"}
PROM_DS = {"type": "prometheus", "uid": "${datasource_prom}"}

# ---------- helpers ----------

def gridpos(x, y, w, h):
    return {"h": h, "w": w, "x": x, "y": y}

def stat_panel(*, pid, title, expr, ds, x, y, w, h, unit="currencyUSD",
               decimals=0, color_mode="value", thresholds=None,
               description="", calc="lastNotNull", graph="area",
               text_mode="auto", just="auto", instant=True, no_value="$0",
               custom_unit=None):
    """
    `instant=True` runs the LogQL/PromQL as an instant query → single value, no
    range-query flicker between refreshes (which is what was happening when the
    last 30s of the [1h] window briefly evaluated to null).
    `no_value` is what shows when the query truly returns nothing (default
    "$0" so the panel never goes black with "No data").
    `custom_unit` lets us show "carts/hour" etc by using Grafana's custom-unit
    string with prefix "suffix:".
    """
    thresholds = thresholds or [
        {"color": "#10B981", "value": None},
    ]
    target = {
        "datasource": ds,
        "refId": "A",
        "expr": expr,
        "legendFormat": "",
    }
    if instant:
        target["instant"] = True
        target["range"] = False
    else:
        target["range"] = True
    real_unit = unit if custom_unit is None else f"suffix:{custom_unit}"
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "description": description,
        "gridPos": gridpos(x, y, w, h),
        "datasource": ds,
        "targets": [target],
        "fieldConfig": {
            "defaults": {
                "unit": real_unit,
                "decimals": decimals,
                "noValue": no_value,
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": thresholds},
            },
            "overrides": [],
        },
        "options": {
            "colorMode": color_mode,
            "graphMode": graph,
            "justifyMode": just,
            "orientation": "auto",
            "percentChangeColorMode": "inverted",
            "reduceOptions": {"calcs": [calc], "fields": "", "values": False},
            "showPercentChange": False,
            "textMode": text_mode,
            "wideLayout": False,
        },
    }


def row(pid, title, y, collapsed=False):
    return {
        "id": pid,
        "type": "row",
        "title": title,
        "gridPos": gridpos(0, y, 24, 1),
        "collapsed": collapsed,
        "panels": [],
    }


def text_panel(pid, content, x, y, w, h, *, transparent=True):
    return {
        "id": pid,
        "type": "text",
        "title": "",
        "transparent": transparent,
        "gridPos": gridpos(x, y, w, h),
        "options": {
            "mode": "markdown",
            "code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False},
            "content": content,
        },
    }


# ---------- new templating ----------
data["templating"]["list"] = [
    {
        "allowCustomValue": True,
        "current": {"selected": True, "text": "grafanacloud-logs", "value": "grafanacloud-logs"},
        "hide": 0,
        "includeAll": False,
        "label": "Loki datasource",
        "multi": False,
        "name": "datasource_loki",
        "options": [],
        "query": "loki",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": False,
        "type": "datasource",
    },
    {
        "allowCustomValue": True,
        "current": {"selected": True, "text": "grafanacloud-prom", "value": "grafanacloud-prom"},
        "hide": 0,
        "includeAll": False,
        "label": "Prometheus datasource",
        "multi": False,
        "name": "datasource_prom",
        "options": [],
        "query": "prometheus",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": False,
        "type": "datasource",
    },
    {
        "current": {"selected": True, "text": "150", "value": "150"},
        "hide": 0,
        "label": "Avg cart-add value ($)",
        "name": "avg_atc_value",
        "options": [{"selected": True, "text": "150", "value": "150"}],
        "query": "150",
        "skipUrlSync": False,
        "type": "textbox",
    },
    {
        "current": {"selected": True, "text": "3", "value": "3"},
        "hide": 0,
        "label": "Outage duration (hours)",
        "name": "outage_hours",
        "options": [{"selected": True, "text": "3", "value": "3"}],
        "query": "3",
        "skipUrlSync": False,
        "type": "textbox",
    },
    {
        "current": {"selected": True, "text": "360", "value": "360"},
        "hide": 0,
        "label": "Baseline ATC / hour",
        "name": "baseline_atc_per_hour",
        "options": [{"selected": True, "text": "360", "value": "360"}],
        "query": "360",
        "skipUrlSync": False,
        "type": "textbox",
    },
    {
        "current": {"selected": True, "text": "8760", "value": "8760"},
        "hide": 0,
        "label": "Annualization (hours/year)",
        "name": "annual_hours",
        "options": [{"selected": True, "text": "8760", "value": "8760"}],
        "query": "8760",
        "skipUrlSync": False,
        "type": "textbox",
    },
]

# ---------- annotations: auto-detected outages ----------
data["annotations"] = {
    "list": [
        {
            "builtIn": 1,
            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True,
            "hide": True,
            "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts",
            "type": "dashboard",
        },
        {
            "datasource": PROM_DS,
            "enable": True,
            "hide": False,
            "iconColor": "rgba(239, 68, 68, 1)",
            "name": "k3s NotReady",
            "expr": 'kube_node_status_condition{cluster="k3s",condition="Ready",status="true"} == 0',
            "step": "1m",
            "titleFormat": "k3s outage — {{node}} NotReady",
            "tagKeys": "node",
        },
        {
            "datasource": PROM_DS,
            "enable": True,
            "hide": False,
            "iconColor": "rgba(251, 146, 60, 1)",
            "name": "Loadgen pod down",
            "expr": 'kube_pod_status_phase{namespace="observibelity",pod=~"k6-traffic-.*",phase!="Running"} == 1',
            "step": "1m",
            "titleFormat": "Loadgen pod {{phase}} — {{pod}}",
            "tagKeys": "pod,phase",
        },
        {
            "datasource": PROM_DS,
            "enable": True,
            "hide": False,
            "iconColor": "rgba(245, 158, 11, 1)",
            "name": "Pod restart",
            "expr": 'changes(kube_pod_container_status_restarts_total{namespace="observibelity",pod=~"k6-traffic-.*|llm-gateway-.*|neoncart-.*|nc-.*"}[5m]) > 0',
            "step": "5m",
            "titleFormat": "Pod restart: {{pod}}",
            "tagKeys": "pod",
        },
    ]
}

# ---------- build panels ----------
P = []

# 200: top revenue pulse (replaces tokens/min sparkline)
revenue_per_min_loki = (
    'sum(rate({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [1m])) * 60 * ${avg_atc_value}'
)
P.append({
    "id": 200,
    "type": "timeseries",
    "title": "",
    "description": "Live revenue pulse — dollars added to carts per minute. Flat ≈ outage.",
    "transparent": True,
    "gridPos": gridpos(0, 0, 24, 3),
    "datasource": LOKI_DS,
    "targets": [{
        "datasource": LOKI_DS, "refId": "A",
        "expr": revenue_per_min_loki, "legendFormat": "$/min", "range": True,
    }],
    "fieldConfig": {
        "defaults": {
            "unit": "currencyUSD",
            "color": {"mode": "thresholds"},
            "custom": {
                "drawStyle": "bars",
                "fillOpacity": 100,
                "gradientMode": "scheme",
                "lineWidth": 0,
                "barAlignment": 0,
                "barWidthFactor": 0.92,
                "showPoints": "never",
                "axisColorMode": "text",
                "axisPlacement": "hidden",
                "axisBorderShow": False,
                "stacking": {"group": "A", "mode": "none"},
                "thresholdsStyle": {"mode": "off"},
                "hideFrom": {"legend": True, "tooltip": False, "viz": False},
                "scaleDistribution": {"type": "linear"},
                "lineInterpolation": "linear",
                "pointSize": 5,
            },
            "thresholds": {
                "mode": "absolute",
                "steps": [
                    {"color": "#10B981", "value": None},
                    {"color": "#34D399", "value": 5},
                    {"color": "#A7F3D0", "value": 50},
                ],
            },
        },
        "overrides": [],
    },
    "options": {
        "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": False},
        "tooltip": {"mode": "single", "sort": "none"},
    },
})

# Row 1 header
y = 3
P.append(row(201, "💰 Revenue right now — what the engine is making", y))
y += 1

# HERO: revenue this hour (instant query — no flicker)
revenue_per_hour_loki = (
    'sum(count_over_time({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [1h])) * ${avg_atc_value}'
)
P.append(stat_panel(
    pid=202, title="Revenue per hour — right now", expr=revenue_per_hour_loki,
    ds=LOKI_DS, x=0, y=y, w=12, h=8,
    color_mode="background", graph="none", instant=True,
    description="Cart-add events in the last 1 hour × avg cart-add value. The pulse of the business.",
    thresholds=[
        {"color": "#EF4444", "value": None},
        {"color": "#F59E0B", "value": 100},
        {"color": "#10B981", "value": 1000},
    ],
))

# 24h revenue
revenue_24h_loki = (
    'sum(count_over_time({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [24h])) * ${avg_atc_value}'
)
P.append(stat_panel(
    pid=203, title="Revenue — last 24 hours", expr=revenue_24h_loki,
    ds=LOKI_DS, x=12, y=y, w=6, h=4,
    color_mode="value", graph="none",
    description="Total cart-add value in the trailing 24 hours.",
))

# Annualized run rate
annualized_loki = (
    'sum(count_over_time({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [24h])) * ${avg_atc_value} * 365'
)
P.append(stat_panel(
    pid=204, title="Annualized run rate", expr=annualized_loki,
    ds=LOKI_DS, x=18, y=y, w=6, h=4,
    color_mode="value", graph="none",
    description="Last 24h revenue × 365. What this engine grosses if today repeats every day for a year.",
    thresholds=[
        {"color": "#10B981", "value": None},
    ],
))

# Per-minute pulse + avg ATC (instant query — no flicker)
revenue_per_min_5m = (
    'sum(rate({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [5m])) * 60 * ${avg_atc_value}'
)
P.append(stat_panel(
    pid=205, title="Per-minute pulse", expr=revenue_per_min_5m,
    ds=LOKI_DS, x=12, y=y+4, w=6, h=4,
    color_mode="value", graph="none", instant=True,
    description="Smoothed 5-minute revenue rate, expressed per minute. Zero means no carts being added.",
    unit="currencyUSD",
))

P.append(stat_panel(
    pid=206, title="Avg cart-add value (tunable)", expr="vector(${avg_atc_value})",
    ds=PROM_DS, x=18, y=y+4, w=6, h=4,
    color_mode="value", graph="none",
    description="Set this to your real average order-line value. Default $150 = midpoint of gift-finder persona budgets.",
))

# ───────────── Row 2: Missed revenue (measured shortfall today) ─────────────
y += 8
P.append(row(230, "📉 Missed revenue — what today's downtime actually cost", y))
y += 1

# HERO: missed revenue today (baseline*24h - actual_24h) * avg value
missed_today_loki = (
    '(${baseline_atc_per_hour} * 24 '
    '- sum(count_over_time({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [24h]))) * ${avg_atc_value}'
)
P.append(stat_panel(
    pid=231, title="Missed revenue today (last 24h)", expr=missed_today_loki,
    ds=LOKI_DS, x=0, y=y, w=12, h=8,
    color_mode="background", graph="area", text_mode="value",
    description=(
        "Measured shortfall: (`baseline_atc_per_hour` × 24h) − today's actual cart-adds, "
        "valued at `avg_atc_value`. Positive = revenue left on the table due to "
        "outages, slowdowns, or capacity caps. Negative = you over-performed baseline."
    ),
    thresholds=[
        {"color": "#10B981", "value": None},       # negative / zero: over-performing → green
        {"color": "#F59E0B", "value": 1},          # any shortfall: amber
        {"color": "#EF4444", "value": 50_000},     # serious shortfall: red
    ],
))

# Missed this hour
missed_hour_loki = (
    '(${baseline_atc_per_hour} '
    '- sum(count_over_time({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [1h]))) * ${avg_atc_value}'
)
P.append(stat_panel(
    pid=232, title="Missed this hour", expr=missed_hour_loki,
    ds=LOKI_DS, x=12, y=y, w=6, h=4,
    color_mode="value", graph="area",
    description="Shortfall in the last 60 minutes vs. baseline. Live bleed indicator.",
    thresholds=[
        {"color": "#10B981", "value": None},
        {"color": "#F59E0B", "value": 1},
        {"color": "#EF4444", "value": 5_000},
    ],
))

# Revenue capture rate (actual / expected) × 100
capture_rate_loki = (
    '(sum(count_over_time({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [24h])) '
    '/ (${baseline_atc_per_hour} * 24)) * 100'
)
P.append(stat_panel(
    pid=233, title="Revenue capture rate (24h)", expr=capture_rate_loki,
    ds=LOKI_DS, x=18, y=y, w=6, h=4,
    color_mode="value", graph="area",
    unit="percent", decimals=1,
    description=(
        "Percent of baseline revenue actually captured today. 100% = matched baseline; "
        "70% = lost ~30% of expected revenue; >100% = beat baseline."
    ),
    thresholds=[
        {"color": "#EF4444", "value": None},
        {"color": "#F59E0B", "value": 70},
        {"color": "#10B981", "value": 95},
    ],
    calc="lastNotNull",
))

# Expected today (baseline math, no Loki call needed)
expected_today_expr = "${baseline_atc_per_hour} * 24 * ${avg_atc_value}"
P.append(stat_panel(
    pid=234, title="Expected today (baseline)", expr=expected_today_expr,
    ds=PROM_DS, x=12, y=y+4, w=6, h=4,
    color_mode="value", graph="none",
    description="What the engine should have produced today at baseline rate.",
    thresholds=[
        {"color": "#9CA3AF", "value": None},
    ],
))

# Actual today (mirror of revenue last 24h but framed against missed)
P.append(stat_panel(
    pid=235, title="Actual today",
    expr=revenue_24h_loki,
    ds=LOKI_DS, x=18, y=y+4, w=6, h=4,
    color_mode="value", graph="area",
    description="Measured revenue in the trailing 24 hours.",
    thresholds=[
        {"color": "#10B981", "value": None},
    ],
))

# ───────────── Row 3: Projected outage cost (scenario / tunable) ─────────────
y += 8
P.append(row(207, "🛑 Projected outage cost — what a future N-hour outage would cost", y))
y += 1

# Top sub-row: markdown explainer (8w) + hero (16w). Hero satisfies the
# hero.too-small lint rule by being ≥ 12w × 8h. Tunables move to a 2nd
# sub-row below at 6w × 4h each (full status palette).
explainer = """### What this means

When the engine is **healthy**, customers add roughly **${baseline_atc_per_hour} carts an hour**, each worth about **\\$${avg_atc_value}**.

That's the revenue you make every hour the lights are on.

When the engine **stops for ${outage_hours} hours**, that hourly revenue evaporates. The red number to the right is the bill.

---

Even a "great" **99 % uptime SLA** still allows **87.6 hours of downtime per year**. At this engine's rate, that's millions of dollars you'll never see.

> **The four boxes at the top of the page tune the math.** Drag them to your own numbers and the whole page updates live."""
P.append(text_panel(208, explainer, x=0, y=y, w=8, h=8))

# HERO: outage cost — 16w × 8h, dynamic title, pure status palette so
# color.mixed-tracks doesn't fire (muted → warning → danger).
outage_cost_expr = "${baseline_atc_per_hour} * ${avg_atc_value} * ${outage_hours}"
P.append(stat_panel(
    pid=209, title="A ${outage_hours}-hour outage costs", expr=outage_cost_expr,
    ds=PROM_DS, x=8, y=y, w=16, h=8,
    color_mode="background", graph="none", text_mode="value", instant=True,
    description="What an outage of `${outage_hours}` hours, at the healthy cart-add rate of `${baseline_atc_per_hour}/hr` and an average cart value of `\\$${avg_atc_value}`, would cost in lost cart-add revenue.",
    thresholds=[
        {"color": "#9CA3AF", "value": None},     # status.muted at 0
        {"color": "#F59E0B", "value": 50_000},   # status.warning amber
        {"color": "#EF4444", "value": 200_000},  # status.danger red
    ],
))

# 2nd sub-row: 4 tunables / supporting stats, each 6w × 4h.
y_sub = y + 8

# (0, +8, 6w × 4h) Outage length
P.append(stat_panel(
    pid=211, title="Outage length", expr="vector(${outage_hours})",
    ds=PROM_DS, x=0, y=y_sub, w=6, h=4,
    color_mode="none", graph="none", text_mode="value", instant=True,
    unit="none", decimals=0, custom_unit=" hours",
    description="Tune this with the textbox at the top of the page.",
    no_value="—",
))

# (6, +8, 6w × 4h) Healthy rate (carts/hour)
P.append(stat_panel(
    pid=212, title="Healthy rate", expr="vector(${baseline_atc_per_hour})",
    ds=PROM_DS, x=6, y=y_sub, w=6, h=4,
    color_mode="none", graph="none", text_mode="value", instant=True,
    unit="none", decimals=0, custom_unit=" carts/hr",
    description="What the engine adds to carts every hour when everything's working. Tune at the top.",
    no_value="—",
))

# (12, +8, 6w × 4h) Bleeding rate
loss_rate_expr = "${baseline_atc_per_hour} * ${avg_atc_value}"
P.append(stat_panel(
    pid=210, title="Bleeding rate (per hour down)", expr=loss_rate_expr,
    ds=PROM_DS, x=12, y=y_sub, w=6, h=4,
    color_mode="value", graph="none", instant=True,
    description="What you lose for every hour the engine is down.",
    thresholds=[
        {"color": "#EF4444", "value": None},
    ],
))

# (18, +8, 6w × 4h) Annual exposure at 99% SLA
annual_99pct_expr = "${baseline_atc_per_hour} * ${avg_atc_value} * (${annual_hours} * 0.01)"
P.append(stat_panel(
    pid=213, title="Annual cost of a 99% SLA", expr=annual_99pct_expr,
    ds=PROM_DS, x=18, y=y_sub, w=6, h=4,
    color_mode="value", graph="none", instant=True,
    description="A 99 % uptime SLA still allows 87.6 hours of downtime per year. This is what those hours cost.",
    thresholds=[
        {"color": "#F59E0B", "value": None},   # status.warning amber (pure track)
    ],
))

# Row 3 header — projected-cost row is now 12 tall (hero 8 + tunables 4)
y += 12
P.append(row(214, "📈 When the engine ran vs. stopped", y))
y += 1

# k3s nodes state timeline
P.append({
    "id": 215,
    "type": "state-timeline",
    "title": "k3s node Ready — green = engine running, red = revenue stopped",
    "description": "Each row is a node. Color = Ready status. Red gaps = no scheduling → loadgen halts → ATC stops → revenue stops.",
    "gridPos": gridpos(0, y, 12, 7),
    "datasource": PROM_DS,
    "targets": [{
        "datasource": PROM_DS, "refId": "A",
        "expr": 'sum by (node) (kube_node_status_condition{cluster="k3s",condition="Ready",status="true"})',
        "legendFormat": "{{node}}", "range": True,
    }],
    "fieldConfig": {
        "defaults": {
            "unit": "short",
            "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#EF4444", "value": None},
                {"color": "#10B981", "value": 1},
            ]},
            "custom": {"fillOpacity": 75, "lineWidth": 0},
            "mappings": [
                {"type": "value", "options": {"0": {"text": "DOWN — $0/hr", "color": "#EF4444", "index": 0},
                                              "1": {"text": "UP — making $", "color": "#10B981", "index": 1}}},
            ],
        },
        "overrides": [],
    },
    "options": {
        "alignValue": "left",
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
        "mergeValues": True, "rowHeight": 0.9, "showValue": "auto",
        "tooltip": {"mode": "single", "sort": "none"},
    },
})

# Customer journey health — single combined strip
# Green = customers can shop (k3s healthy + critical pods Running)
# Red   = customers locked out (at least one critical signal is broken)
journey_health_expr = (
    'clamp_max('
    'min(kube_node_status_condition{cluster="k3s",condition="Ready",status="true"}) '
    '* clamp_max((count(kube_pod_status_phase{namespace="observibelity",pod=~"k6-traffic-.*",phase="Running"} == 1) or vector(0)), 1) '
    '* clamp_max((count(kube_pod_status_phase{namespace="observibelity",pod=~"neoncart-.*",phase="Running"} == 1) or vector(0)), 1) '
    '* clamp_max((count(kube_pod_status_phase{namespace="observibelity",pod=~"llm-gateway-.*",phase="Running"} == 1) or vector(0)), 1)'
    ', 1)'
)
P.append({
    "id": 216,
    "type": "state-timeline",
    "title": "Customer journey health — can shoppers reach checkout?",
    "description": (
        "1 = every component a customer needs is up (k3s nodes Ready, k6 driving traffic, "
        "neoncart serving the website, llm-gateway handling chats). Any one of those breaking "
        "drops this to 0 — customers either can't reach the site or hit an error before checkout. "
        "This is the same signal that turns 'Lost revenue' on in the chart below."
    ),
    "gridPos": gridpos(12, y, 12, 7),
    "datasource": PROM_DS,
    "targets": [{
        "datasource": PROM_DS, "refId": "A",
        "expr": journey_health_expr,
        "legendFormat": "customer journey",
        "range": True,
    }],
    "fieldConfig": {
        "defaults": {
            "unit": "short",
            "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#EF4444", "value": None},
                {"color": "#10B981", "value": 1},
            ]},
            "custom": {"fillOpacity": 85, "lineWidth": 0},
            "mappings": [
                {"type": "value", "options": {
                    "0": {"text": "Customers locked out", "color": "#EF4444", "index": 0},
                    "1": {"text": "Customers can shop", "color": "#10B981", "index": 1},
                }},
            ],
        },
        "overrides": [],
    },
    "options": {
        "alignValue": "left",
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": False},
        "mergeValues": True, "rowHeight": 0.9, "showValue": "auto",
        "tooltip": {"mode": "single", "sort": "none"},
    },
})

# Row 4 header
y += 7
P.append(row(217, "📊 Revenue per 10-minute block — what we made, what we missed", y))
y += 1

# 218: Actual revenue per 10-min block, stacked by model
# (count over a 10-min window evaluated every 10 min = non-overlapping 10-min buckets,
#  exactly like the billing dashboard's monthly bars.)
actual_by_model_10m = (
    'sum by (model) ('
    'count_over_time('
    '{service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" '
    '| regexp `model=(?P<model>[a-zA-Z0-9._:-]+)` '
    '[10m]'
    ')'
    ') * ${avg_atc_value}'
)
P.append({
    "id": 218,
    "type": "timeseries",
    "title": "What we made — per 10-minute block, stacked by model",
    "description": (
        "Each bar = total cart-add revenue in a 10-minute window, broken down by which model "
        "drove the conversation. Hover a bar to see the model mix. Legend on the right shows "
        "trailing 24 h totals."
    ),
    "gridPos": gridpos(0, y, 24, 9),
    "datasource": LOKI_DS,
    "targets": [
        {
            "datasource": LOKI_DS, "refId": "A",
            "expr": actual_by_model_10m,
            "legendFormat": "{{model}}",
            "range": True,
            "step": "10m",
        },
    ],
    "fieldConfig": {
        "defaults": {
            "unit": "currencyUSD",
            "decimals": 0,
            # palette-classic-by-name keeps "claude-haiku" the same hue across
            # every panel + across time-window changes; per-model byName
            # overrides from the aesthetic pass pin the exact hex.
            "color": {"mode": "palette-classic-by-name"},
            "custom": {
                "drawStyle": "bars",
                "fillOpacity": 95,
                "gradientMode": "none",
                "lineWidth": 0,
                "barAlignment": 0,
                "barWidthFactor": 0.96,
                "showPoints": "never",
                "showValue": "auto",
                "thresholdsStyle": {"mode": "off"},
                "stacking": {"group": "A", "mode": "normal"},
                "scaleDistribution": {"type": "linear"},
            },
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#10B981", "value": None},
            ]},
        },
        "overrides": [],
    },
    "options": {
        "legend": {
            "calcs": ["sum", "mean", "max"],
            "displayMode": "table",
            "placement": "right",
            "showLegend": True,
            "sortBy": "Total",
            "sortDesc": True,
        },
        "tooltip": {"mode": "multi", "sort": "desc"},
    },
})

# 240: Missed revenue per 10-min block — gated by detected k3s/critical-pod errors.
# Lost revenue turns ON only when something is wrong, and stays on until the error
# clears. The gate is the fraction of the 10-min window where at least one of:
#   - a k3s node is NotReady, or
#   - a critical pod (k6-traffic, neoncart, llm-gateway) is in a non-Running phase
# is true. avg_over_time(gate[10m:1m]) gives 0.0 = healthy, 1.0 = full 10m down,
# 0.5 = down half the window. Multiplied by expected revenue per 10-min, we get
# missed $ exactly proportional to the error duration. Yin/yang with panel 218.
missed_per_10m_gated = (
    '(${baseline_atc_per_hour} / 6 * ${avg_atc_value}) '
    '* avg_over_time(('
    'clamp_max('
    '(sum(kube_node_status_condition{cluster="k3s",condition="Ready",status="false"} == 1) or vector(0)) '
    '+ (sum(kube_pod_status_phase{namespace="observibelity",pod=~"k6-traffic-.*|neoncart-.*|llm-gateway-.*",phase!="Running"} == 1) or vector(0)),'
    ' 1)'
    ')[10m:1m])'
)
P.append({
    "id": 240,
    "type": "timeseries",
    "title": "Lost revenue — gated by k3s / critical-pod errors",
    "description": (
        "Turns ON when an error is firing on k3s or a critical pod (k6-traffic, neoncart, "
        "llm-gateway) and stays ON until the error clears. Value per 10-min bar = expected "
        "revenue × fraction of the window the error was firing. Yin/yang with the 'What we "
        "made' chart above — when one is green, the other should be empty."
    ),
    "gridPos": gridpos(0, y + 9, 24, 8),
    "datasource": PROM_DS,
    "targets": [
        {
            "datasource": PROM_DS, "refId": "A",
            "expr": missed_per_10m_gated,
            "legendFormat": "lost while errors firing",
            "range": True,
            "step": "10m",
            "interval": "10m",
        },
    ],
    "fieldConfig": {
        "defaults": {
            "unit": "currencyUSD",
            "decimals": 0,
            "min": 0,
            "color": {"mode": "thresholds"},
            "custom": {
                "drawStyle": "bars",
                "fillOpacity": 95,
                "gradientMode": "none",
                "lineWidth": 0,
                "barAlignment": 0,
                "barWidthFactor": 0.96,
                "showPoints": "never",
                "showValue": "auto",
                "thresholdsStyle": {"mode": "off"},
                "stacking": {"group": "A", "mode": "none"},
            },
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "transparent", "value": None},
                {"color": "#EF4444", "value": 1},
            ]},
        },
        "overrides": [
            {
                "matcher": {"id": "byName", "options": "lost while errors firing"},
                "properties": [
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "#EF4444"}},
                ],
            },
        ],
    },
    "options": {
        "legend": {
            "calcs": ["sum", "max", "mean"],
            "displayMode": "table",
            "placement": "right",
            "showLegend": True,
        },
        "tooltip": {"mode": "multi", "sort": "desc"},
    },
})

# Row 5 header — combined height: 9 (actual) + 8 (missed) = 17
y += 17
P.append(row(219, "🎯 Where the revenue came from", y))
y += 1

# Bar gauge by model
P.append({
    "id": 220,
    "type": "bargauge",
    "title": "Revenue mix by model — last 24h",
    "description": "Which models drove cart-add events. Higher = more revenue contribution.",
    "gridPos": gridpos(0, y, 12, 8),
    "datasource": LOKI_DS,
    "targets": [{
        "datasource": LOKI_DS, "refId": "A",
        "expr": (
            'sum by (model) (count_over_time({service_namespace="observibelity",container="tool"} '
            '|~ "atc_event source=loadgen" | regexp `model=(?P<model>[a-zA-Z0-9._:-]+)` [24h])) * ${avg_atc_value}'
        ),
        "legendFormat": "{{model}}", "range": False, "instant": True,
    }],
    "fieldConfig": {
        "defaults": {
            "unit": "currencyUSD",
            "decimals": 0,
            "color": {"mode": "palette-classic"},
            "thresholds": {"mode": "absolute", "steps": [{"color": "#10B981", "value": None}]},
        },
        "overrides": [],
    },
    "options": {
        "displayMode": "gradient",
        "orientation": "horizontal",
        "showUnfilled": True,
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "valueMode": "color",
    },
})

# Top products
P.append({
    "id": 221,
    "type": "bargauge",
    "title": "Top products by revenue — last 24h",
    "description": "Top 10 SKUs that ended up in carts.",
    "gridPos": gridpos(12, y, 12, 8),
    "datasource": LOKI_DS,
    "targets": [{
        "datasource": LOKI_DS, "refId": "A",
        "expr": (
            'topk(10, sum by (sku) (count_over_time({service_namespace="observibelity",container="tool"} '
            '|~ "atc_event source=loadgen" | regexp `sku=(?P<sku>[A-Z0-9.-]+)` [24h]))) * ${avg_atc_value}'
        ),
        "legendFormat": "{{sku}}", "range": False, "instant": True,
    }],
    "fieldConfig": {
        "defaults": {
            "unit": "currencyUSD",
            "decimals": 0,
            "color": {"mode": "palette-classic"},
            "thresholds": {"mode": "absolute", "steps": [{"color": "#10B981", "value": None}]},
        },
        "overrides": [],
    },
    "options": {
        "displayMode": "gradient",
        "orientation": "horizontal",
        "showUnfilled": True,
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "valueMode": "color",
    },
})

# Row 6 header — ROI math
y += 8
P.append(row(222, "💡 Why this dashboard pays for itself", y))
y += 1

roi_content = """### The math, for finance

| Metric | Formula | Why it matters |
|---|---|---|
| **Annual run rate** | `(24-hour revenue) × 365` | What this AI workload contributes to the top line at today's pace |
| **Loss rate** | `Baseline ATC/hr × Avg cart-add value` | The bleed rate the moment the engine stops |
| **Cost of a single outage** | `Loss rate × Outage hours` | The headline number above |
| **Cost of 99 % uptime SLA** | `Loss rate × 87.6 hr` | The annual cost of a "great" 99 % SLA. Most platforms target 99.9 % (8.76 hr) or 99.99 % (52 min). |
| **Observability ROI** | `(Cost of outages prevented) / (Annual platform cost)` | If avoiding one 3-hour outage pays for the year, the platform is profit. |

> **The pitch.** The dashboard above shows the engine in production. Every flat spot in the green bars is a moment we made nothing. Observability is what turns those flat spots from "noticed in next week's QBR" into "paged in 90 seconds." Multiply by the loss rate to see what each minute of MTTR is worth.
"""
P.append(text_panel(223, roi_content, x=0, y=y, w=24, h=10))
y += 10

# Apply
data["panels"] = P
data["title"] = "AI Obs — Cost of an Outage (live revenue × downtime impact)"
data["description"] = (
    "Business / finops view: live cart-add revenue rate, projected loss when k3s goes down, "
    "and the ROI math. Tune the four variables at top (avg cart-add value, outage hours, "
    "baseline ATC/hr, annual hours) to drive the numbers."
)
data["tags"] = ["ai-observability", "observibelity", "outage-cost", "atc", "finops", "revenue", "demo"]
data["refresh"] = "30s"
data["schemaVersion"] = 42

DASH.write_text(json.dumps(data, indent=2) + "\n")
print(f"Wrote {DASH} with {len(P)} panels.")
