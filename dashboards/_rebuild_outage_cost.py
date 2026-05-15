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
               text_mode="auto", just="auto"):
    thresholds = thresholds or [
        {"color": "#10B981", "value": None},
    ]
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "description": description,
        "gridPos": gridpos(x, y, w, h),
        "datasource": ds,
        "targets": [
            {
                "datasource": ds,
                "refId": "A",
                "expr": expr,
                "legendFormat": "",
                "range": True,
            }
        ],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "decimals": decimals,
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

# ---------- annotations: pod restarts ----------
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
            "name": "Pod restart",
            "expr": 'changes(kube_pod_container_status_restarts_total{namespace="observibelity",pod=~"k6-traffic-.*|llm-gateway-.*"}[5m]) > 0',
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
    '|~ "atc_event source=loadgen" [$__rate_interval])) * 60 * ${avg_atc_value}'
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

# HERO: revenue this hour
revenue_per_hour_loki = (
    'sum(count_over_time({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [1h])) * ${avg_atc_value}'
)
P.append(stat_panel(
    pid=202, title="Revenue per hour — right now", expr=revenue_per_hour_loki,
    ds=LOKI_DS, x=0, y=y, w=12, h=8,
    color_mode="background", graph="area",
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

# Per-minute pulse + avg ATC
revenue_per_min_5m = (
    'sum(rate({service_namespace="observibelity",container="tool"} '
    '|~ "atc_event source=loadgen" [5m])) * 60 * ${avg_atc_value}'
)
P.append(stat_panel(
    pid=205, title="Per-minute pulse", expr=revenue_per_min_5m,
    ds=LOKI_DS, x=12, y=y+4, w=6, h=4,
    color_mode="value", graph="area",
    description="Smoothed 5-minute revenue rate, expressed per minute. Zero means no carts being added.",
    unit="currencyUSD",
))

P.append(stat_panel(
    pid=206, title="Avg cart-add value (tunable)", expr="vector(${avg_atc_value})",
    ds=PROM_DS, x=18, y=y+4, w=6, h=4,
    color_mode="value", graph="none",
    description="Set this to your real average order-line value. Default $150 = midpoint of gift-finder persona budgets.",
))

# Row 2 header
y += 8
P.append(row(207, "🛑 Cost if the engine stops — what an outage costs the business", y))
y += 1

# Markdown explainer
explainer = """### How we calculate

**Loss rate ($/hour)** = `Baseline ATC / hour` × `Avg cart-add value`
**Outage cost** = `Loss rate` × `Outage duration`
**Annual exposure** = `Loss rate` × `1% × 8 760` (= 87.6 hr/yr)

> Tune the four variables at the top of the page to drive the numbers live.
> Default baseline (`360 / hr`) ≈ the p75 of a healthy week.
> Even a 99 % uptime SLA still bleeds **87 hours / yr** at the loss rate shown."""
P.append(text_panel(208, explainer, x=0, y=y, w=8, h=8))

# HERO: outage cost
outage_cost_expr = "${baseline_atc_per_hour} * ${avg_atc_value} * ${outage_hours}"
P.append(stat_panel(
    pid=209, title="Cost of this outage", expr=outage_cost_expr,
    ds=PROM_DS, x=8, y=y, w=8, h=8,
    color_mode="background", graph="none", text_mode="value",
    description="What a `${outage_hours}` hour outage at baseline rate costs you in cart-add revenue.",
    thresholds=[
        {"color": "#F472B6", "value": None},
        {"color": "#FB923C", "value": 50_000},
        {"color": "#EF4444", "value": 200_000},
    ],
))

# Loss rate
loss_rate_expr = "${baseline_atc_per_hour} * ${avg_atc_value}"
P.append(stat_panel(
    pid=210, title="Loss rate", expr=loss_rate_expr,
    ds=PROM_DS, x=16, y=y, w=8, h=4,
    color_mode="value", graph="none",
    description="How fast you bleed revenue while the engine is down.",
    thresholds=[
        {"color": "#EF4444", "value": None},
    ],
))

# Tunables row of 3
P.append(stat_panel(
    pid=211, title="Outage hours", expr="vector(${outage_hours})",
    ds=PROM_DS, x=16, y=y+4, w=3, h=4,
    color_mode="none", graph="none", text_mode="value",
    unit="h", decimals=1,
    description="Tune above.",
))
P.append(stat_panel(
    pid=212, title="Baseline ATC/hr", expr="vector(${baseline_atc_per_hour})",
    ds=PROM_DS, x=19, y=y+4, w=2, h=4,
    color_mode="none", graph="none", text_mode="value",
    unit="short", decimals=0,
    description="Tune above.",
))
annual_99pct_expr = "${baseline_atc_per_hour} * ${avg_atc_value} * (${annual_hours} * 0.01)"
P.append(stat_panel(
    pid=213, title="Annual @ 99% SLA", expr=annual_99pct_expr,
    ds=PROM_DS, x=21, y=y+4, w=3, h=4,
    color_mode="value", graph="none",
    description="What 1% downtime/yr (87.6 hr) costs at this loss rate.",
    thresholds=[
        {"color": "#FB923C", "value": None},
    ],
))

# Row 3 header
y += 8
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

# k6 traffic pod state
P.append({
    "id": 216,
    "type": "state-timeline",
    "title": "Loadgen pod state — restarts/crashes show as color breaks",
    "description": "k6 is the engine driving cart-adds. Breaks here = downstream revenue drops.",
    "gridPos": gridpos(12, y, 12, 7),
    "datasource": PROM_DS,
    "targets": [{
        "datasource": PROM_DS, "refId": "A",
        "expr": 'max by (pod, phase) (kube_pod_status_phase{namespace="observibelity",pod=~"k6-traffic-.*"} == 1)',
        "legendFormat": "{{pod}} {{phase}}", "range": True,
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

# Row 4 header
y += 7
P.append(row(217, "💵 Revenue flow over time — where the money was (and wasn't)", y))
y += 1

# Big revenue timeseries
P.append({
    "id": 218,
    "type": "timeseries",
    "title": "Cart-add revenue — $/hour",
    "description": "Each bar = the previous 5 min of ATC events × avg value, scaled to $/hour. Flat = outage. Pod-restart annotations marked in red.",
    "gridPos": gridpos(0, y, 24, 8),
    "datasource": LOKI_DS,
    "targets": [
        {
            "datasource": LOKI_DS, "refId": "A",
            "expr": (
                'sum(rate({service_namespace="observibelity",container="tool"} '
                '|~ "atc_event source=loadgen" [5m])) * 3600 * ${avg_atc_value}'
            ),
            "legendFormat": "$/hour (live)", "range": True,
        },
        {
            "datasource": PROM_DS, "refId": "B",
            "expr": "${baseline_atc_per_hour} * ${avg_atc_value}",
            "legendFormat": "baseline $/hour", "range": True,
        },
    ],
    "fieldConfig": {
        "defaults": {
            "unit": "currencyUSD",
            "color": {"mode": "thresholds"},
            "custom": {
                "drawStyle": "bars",
                "fillOpacity": 70,
                "gradientMode": "opacity",
                "lineWidth": 1,
                "barAlignment": 0,
                "barWidthFactor": 0.92,
                "showPoints": "never",
                "thresholdsStyle": {"mode": "off"},
                "stacking": {"group": "A", "mode": "none"},
            },
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#10B981", "value": None},
            ]},
        },
        "overrides": [
            {
                "matcher": {"id": "byName", "options": "baseline $/hour"},
                "properties": [
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "#9CA3AF"}},
                    {"id": "custom.drawStyle", "value": "line"},
                    {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}},
                    {"id": "custom.lineWidth", "value": 2},
                    {"id": "custom.fillOpacity", "value": 0},
                ],
            },
            {
                "matcher": {"id": "byName", "options": "$/hour (live)"},
                "properties": [
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "#10B981"}},
                ],
            },
        ],
    },
    "options": {
        "legend": {"calcs": ["mean", "max", "min"], "displayMode": "table", "placement": "right", "showLegend": True},
        "tooltip": {"mode": "multi", "sort": "desc"},
    },
})

# Row 5 header
y += 8
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
