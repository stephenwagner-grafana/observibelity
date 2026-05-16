#!/usr/bin/env python3
"""
Rebuild ai-obs-loadgen.json — the story of what loadgen is driving + how the
gateway routes traffic.

Panels prove out, in order:
  1. Live hero row (current state)
  2. The calm beach wave (request rate by provider over time)
  3. Ollama saturation + spillover correlation (in-flight + threshold + events)
  4. Ollama model rotation timeline (which model is active per 5-min window)
  5. Claude budget burndown ($ spent today vs $20 ceiling)
  6. Per-specialist request rate (who's calling)
  7. Errors + tool-strip retries (gateway log-derived)
"""
import json
from pathlib import Path

DASH = Path(__file__).parent / "ai-obs-loadgen.json"

PROM_DS = {"type": "prometheus", "uid": "${datasource_prom}"}
LOKI_DS = {"type": "loki", "uid": "${datasource_loki}"}

GREEN  = "#10B981"
AMBER  = "#F59E0B"
RED    = "#EF4444"
CYAN   = "#67E8F9"
PINK   = "#F472B6"
PURPLE = "#A78BFA"
BLUE   = "#8AB8FF"
ORANGE = "#FB923C"
MUTED  = "#9CA3AF"


def gp(x, y, w, h):
    return {"h": h, "w": w, "x": x, "y": y}


def stat(*, pid, title, desc, expr, x, y, w, h, ds=PROM_DS, unit="short",
         decimals=0, thresholds=None, color_mode="value", graph="none",
         instant=True, text_mode="auto"):
    thresholds = thresholds or [{"color": GREEN, "value": None}]
    return {
        "id": pid, "type": "stat", "title": title, "description": desc,
        "datasource": ds, "gridPos": gp(x, y, w, h),
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "decimals": decimals,
                "unit": unit,
                "thresholds": {"mode": "absolute", "steps": thresholds},
            },
            "overrides": [],
        },
        "options": {
            "colorMode": color_mode, "graphMode": graph,
            "justifyMode": "center", "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": text_mode, "wideLayout": False,
        },
        "targets": [{"datasource": ds, "expr": expr, "instant": instant, "refId": "A"}],
    }


def timeseries(*, pid, title, desc, targets, x, y, w, h, ds=PROM_DS, unit="short",
               decimals=1, draw_style="line", fill=15, legend_calcs=None,
               threshold_lines=None, stacking=None):
    legend_calcs = legend_calcs or ["mean", "last"]
    overrides = []
    if threshold_lines:
        for label, value, color in threshold_lines:
            overrides.append({
                "matcher": {"id": "byFrameRefID", "options": label},
                "properties": [
                    {"id": "custom.lineStyle", "value": {"dash": [6, 6], "fill": "dash"}},
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": color}},
                ],
            })
    field_config = {
        "defaults": {
            "color": {"mode": "palette-classic"},
            "custom": {
                "drawStyle": draw_style, "fillOpacity": fill,
                "gradientMode": "opacity" if draw_style == "line" else "none",
                "lineInterpolation": "smooth", "lineWidth": 2,
                "pointSize": 0, "showPoints": "never", "spanNulls": True,
            },
            "decimals": decimals,
            "unit": unit,
        },
        "overrides": overrides,
    }
    if stacking:
        field_config["defaults"]["custom"]["stacking"] = {"mode": stacking, "group": "A"}
    return {
        "id": pid, "type": "timeseries", "title": title, "description": desc,
        "datasource": ds, "gridPos": gp(x, y, w, h),
        "fieldConfig": field_config,
        "options": {
            "legend": {"displayMode": "table", "placement": "right", "showLegend": True, "calcs": legend_calcs},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": targets,
    }


def row(*, pid, title, x, y):
    return {
        "id": pid, "type": "row", "title": title,
        "collapsed": False, "gridPos": gp(x, y, 24, 1),
        "panels": [], "datasource": None, "targets": [],
    }


def text(*, pid, content, x, y, w, h):
    return {
        "id": pid, "type": "text", "title": "",
        "gridPos": gp(x, y, w, h),
        "options": {"mode": "markdown", "content": content},
    }


def state_timeline(*, pid, title, desc, targets, x, y, w, h, ds=PROM_DS,
                   mappings=None):
    mappings = mappings or []
    return {
        "id": pid, "type": "state-timeline", "title": title, "description": desc,
        "datasource": ds, "gridPos": gp(x, y, w, h),
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {"fillOpacity": 75, "lineWidth": 0},
                "mappings": mappings,
                "unit": "short",
            },
            "overrides": [],
        },
        "options": {
            "alignValue": "left",
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "mergeValues": True, "rowHeight": 0.9, "showValue": "auto",
            "tooltip": {"mode": "single", "sort": "none"},
        },
        "targets": targets,
    }


# ============================================================================

panels = []
y = 0

# ---- intro readme -----------------------------------------------------------
panels.append(text(
    pid=10, x=0, y=y, w=24, h=3,
    content=(
        "## How loadgen routes traffic\n"
        "**1.** k6 sends every request to **Ollama** (no static ratio, no probability roll). "
        "**2.** Gateway tracks `ollama.in_flight`; once it hits **OLLAMA_SATURATION_THRESHOLD** (8 = NUM_PARALLEL on .240), "
        "**3.** New `target=ollama` requests get rerouted to **Claude** — IF today's running cost is below **`$20`**. "
        "**4.** When Claude's daily budget is gone, requests stay on Ollama and accept queue latency.\n"
        "_Process, not a ratio. Spillover events + budget burn appear below._"
    ),
))
y += 3

# ---- Hero row: live state ---------------------------------------------------
panels.append(row(pid=20, title="🟢 Right now — what the loadgen + gateway are doing", x=0, y=y))
y += 1

panels.append(stat(
    pid=21, x=0, y=y, w=6, h=4,
    title="Requests / sec — Ollama",
    desc="5m rolling rate of /v1/complete calls that landed on Ollama.",
    expr='sum(rate(gen_ai_client_operation_duration_seconds_count{gen_ai_system="ollama"}[5m]))',
    unit="reqps", decimals=2,
    thresholds=[{"color": GREEN, "value": None}],
    color_mode="value", graph="area",
))
panels.append(stat(
    pid=22, x=6, y=y, w=6, h=4,
    title="Requests / sec — Claude (spillover)",
    desc="5m rate of calls that ended up on Anthropic. With claudeFraction=0, every Claude call came from saturation spillover.",
    expr='sum(rate(gen_ai_client_operation_duration_seconds_count{gen_ai_system="anthropic"}[5m]))',
    unit="reqps", decimals=2,
    thresholds=[{"color": MUTED, "value": None}, {"color": PINK, "value": 0.01}],
    color_mode="value", graph="area",
))
panels.append(stat(
    pid=23, x=12, y=y, w=6, h=4,
    title="Ollama in-flight (live)",
    desc=(
        "Concurrent Ollama requests on this gateway pod. Hits the "
        "OLLAMA_SATURATION_THRESHOLD (8 by default) → spillover fires."
    ),
    expr='avg(llm_gateway_ollama_in_flight)',
    unit="short", decimals=1,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": AMBER, "value": 6},
        {"color": PINK, "value": 8},
    ],
    color_mode="background", graph="area",
))
panels.append(stat(
    pid=24, x=18, y=y, w=6, h=4,
    title="Spillover events / hour",
    desc='Times the gateway swapped target=ollama → anthropic because Ollama hit the threshold AND the daily budget had room.',
    expr='sum(increase(llm_gateway_spillover_total[1h]))',
    unit="short", decimals=0,
    thresholds=[{"color": MUTED, "value": None}, {"color": PURPLE, "value": 1}],
    color_mode="value", graph="area",
))
y += 4

# ---- Budget burndown stats --------------------------------------------------
panels.append(stat(
    pid=31, x=0, y=y, w=8, h=4,
    title="💰 Claude spent today",
    desc="Cumulative Anthropic spend (USD) for the current UTC day. The dispatcher denies further spillover once this reaches the budget ceiling.",
    expr='max(llm_gateway_claude_daily_spend_usd)',
    unit="currencyUSD", decimals=2,
    thresholds=[
        {"color": GREEN, "value": None},
        {"color": AMBER, "value": 15},
        {"color": RED, "value": 20},
    ],
    color_mode="background", graph="area",
))
panels.append(stat(
    pid=32, x=8, y=y, w=8, h=4,
    title="🪙 Budget remaining",
    desc="$20/day - spent. When this hits 0, spillover stops and saturation-overflow stays on Ollama (with queue latency).",
    expr='max(llm_gateway_claude_daily_budget_usd) - max(llm_gateway_claude_daily_spend_usd)',
    unit="currencyUSD", decimals=2,
    thresholds=[
        {"color": RED, "value": None},
        {"color": AMBER, "value": 5},
        {"color": GREEN, "value": 10},
    ],
    color_mode="value", graph="none",
))
panels.append(stat(
    pid=33, x=16, y=y, w=8, h=4,
    title="🧰 Tool-strip retries / 5m",
    desc='When the active Ollama model lacks tool-call support (e.g. tinyllama), the gateway catches the 400 and retries without tools. This counts those silent fallbacks.',
    expr=(
        'sum(count_over_time({service_namespace="observibelity",container="llm-gateway"} '
        '|~ "no-tools.*retrying without tools" [5m]))'
    ),
    ds=LOKI_DS, unit="short", decimals=0,
    thresholds=[{"color": MUTED, "value": None}, {"color": ORANGE, "value": 1}],
    color_mode="value", graph="area",
))
y += 4

# ---- The wave ---------------------------------------------------------------
panels.append(row(pid=40, title="🌊 The calm beach wave — request rate by provider", x=0, y=y))
y += 1
panels.append(timeseries(
    pid=41, x=0, y=y, w=24, h=8,
    title="Rate by provider (req/s)",
    desc="Ollama gets everything by default. Claude only shows up when Ollama saturates AND the budget has room. The two lines together prove the spillover process is what determines provider choice — not a ratio.",
    targets=[
        {
            "datasource": PROM_DS,
            "expr": 'sum(rate(gen_ai_client_operation_duration_seconds_count{gen_ai_system="ollama"}[5m]))',
            "legendFormat": "ollama",
            "refId": "A",
        },
        {
            "datasource": PROM_DS,
            "expr": 'sum(rate(gen_ai_client_operation_duration_seconds_count{gen_ai_system="anthropic"}[5m]))',
            "legendFormat": "anthropic (spillover)",
            "refId": "B",
        },
    ],
    unit="reqps", decimals=2, fill=20,
))
y += 8

# ---- Saturation + spillover correlation ------------------------------------
panels.append(row(pid=50, title="🚦 Saturation drives spillover", x=0, y=y))
y += 1
panels.append(timeseries(
    pid=51, x=0, y=y, w=12, h=8,
    title="Ollama in-flight vs threshold",
    desc='Live in-flight count averaged across gateway pods. When it crosses 8 (the OLLAMA_SATURATION_THRESHOLD), the dispatcher starts spilling.',
    targets=[
        {"datasource": PROM_DS, "expr": "avg(llm_gateway_ollama_in_flight)", "legendFormat": "in_flight", "refId": "A"},
        {"datasource": PROM_DS, "expr": "vector(8)", "legendFormat": "saturation threshold", "refId": "B"},
    ],
    unit="short", decimals=1, fill=10,
    threshold_lines=[("B", 8, RED)],
))
panels.append(timeseries(
    pid=52, x=12, y=y, w=12, h=8,
    title="Spillover events / minute",
    desc="Bar = number of times in the last minute the dispatcher swapped target=ollama → anthropic. Should rise during Ollama saturation, drop when the budget exhausts.",
    targets=[
        {
            "datasource": PROM_DS,
            "expr": 'sum(rate(llm_gateway_spillover_total[5m])) * 60',
            "legendFormat": "spillover/min",
            "refId": "A",
        },
    ],
    unit="short", decimals=1, fill=40, draw_style="bars",
))
y += 8

# ---- Budget burndown -------------------------------------------------------
panels.append(timeseries(
    pid=61, x=0, y=y, w=24, h=8,
    title="💰 Claude daily spend vs $20 budget",
    desc="Cumulative $ spent on Anthropic today. Resets at UTC midnight. The dashed line at $20 is the hard ceiling — once spent crosses it, the gateway stops spilling for the rest of the UTC day.",
    targets=[
        {"datasource": PROM_DS, "expr": "max(llm_gateway_claude_daily_spend_usd)", "legendFormat": "spent today", "refId": "A"},
        {"datasource": PROM_DS, "expr": "max(llm_gateway_claude_daily_budget_usd)", "legendFormat": "$20 budget", "refId": "B"},
    ],
    unit="currencyUSD", decimals=2, fill=20,
    threshold_lines=[("B", 20, AMBER)],
))
y += 8

# ---- Ollama model rotation timeline ----------------------------------------
panels.append(row(pid=70, title="🔄 Ollama rotation — one model per 5-min window", x=0, y=y))
y += 1
panels.append(timeseries(
    pid=71, x=0, y=y, w=24, h=7,
    title="Active model — rate by gen_ai.request.model (Ollama only)",
    desc="Per-model request rate. With prewarm + OLLAMA_MAX_LOADED_MODELS=2, each window's model takes over hot — no cold-load notch at the 5-min boundary.",
    targets=[
        {
            "datasource": PROM_DS,
            "expr": (
                'sum by (gen_ai_request_model) '
                '(rate(gen_ai_client_operation_duration_seconds_count{gen_ai_system="ollama"}[5m]))'
            ),
            "legendFormat": "{{gen_ai_request_model}}",
            "refId": "A",
        },
    ],
    unit="reqps", decimals=2, fill=15, stacking="normal",
))
y += 7

# ---- Per-specialist load ---------------------------------------------------
panels.append(row(pid=80, title="🤖 Who's calling — load by specialist", x=0, y=y))
y += 1
panels.append(timeseries(
    pid=81, x=0, y=y, w=24, h=7,
    title="Request rate by ai_o11y.specialist",
    desc="nc-chatbot, sb-router, nc-gift-finder, etc. — the specialists doing the actual chatting. baseline.js's scenario table drives the mix.",
    targets=[
        {
            "datasource": PROM_DS,
            "expr": (
                'sum by (ai_o11y_specialist) '
                '(rate(gen_ai_client_operation_duration_seconds_count{ai_o11y_specialist!=""}[5m]))'
            ),
            "legendFormat": "{{ai_o11y_specialist}}",
            "refId": "A",
        },
    ],
    unit="reqps", decimals=2, fill=15,
))
y += 7

# ---- Errors + latency ------------------------------------------------------
panels.append(row(pid=90, title="❌ Errors + tail latency", x=0, y=y))
y += 1
panels.append(timeseries(
    pid=91, x=0, y=y, w=12, h=7,
    title="Gateway error rate (4xx + 5xx)",
    desc="From the gateway access log. Spikes here = real upstream failures. Tool-strip 400s should NOT show — the gateway catches and retries.",
    targets=[{
        "datasource": LOKI_DS,
        "expr": (
            'sum(rate({service_namespace="observibelity",container="llm-gateway"} '
            '|~ "POST /v1/complete.* [45]\\\\d\\\\d" [5m]))'
        ),
        "legendFormat": "errors/sec",
        "refId": "A",
    }],
    unit="short", decimals=2, fill=20,
))
panels.append(timeseries(
    pid=92, x=12, y=y, w=12, h=7,
    title="Provider p95 latency",
    desc="histogram_quantile p95 over the gen_ai_client_operation_duration_seconds histogram. Wave dips ≠ latency spikes anymore now that prewarm keeps the next model hot.",
    targets=[
        {
            "datasource": PROM_DS,
            "expr": (
                'histogram_quantile(0.95, sum by (le, gen_ai_system) '
                '(rate(gen_ai_client_operation_duration_seconds_bucket[5m])))'
            ),
            "legendFormat": "{{gen_ai_system}}",
            "refId": "A",
        },
    ],
    unit="s", decimals=2, fill=15,
))
y += 7

# ---- Dashboard wrap --------------------------------------------------------
dashboard = {
    "uid": "ai-obs-loadgen",
    "title": "AI o11y — Loadgen Activity (Ollama-first + spillover process)",
    "tags": ["ai-observability", "loadgen", "k6", "operations", "observibelity", "spillover"],
    "schemaVersion": 39,
    "version": 1,
    "refresh": "30s",
    "time": {"from": "now-1h", "to": "now"},
    "timezone": "",
    "templating": {
        "list": [
            {
                "name": "datasource_prom", "label": "Prometheus", "type": "datasource",
                "query": "prometheus", "current": {"selected": True, "text": "grafanacloud-stephenwagner-prom", "value": "grafanacloud-prom"},
                "hide": 0, "skipUrlSync": False, "includeAll": False, "multi": False, "options": [],
            },
            {
                "name": "datasource_loki", "label": "Loki", "type": "datasource",
                "query": "loki", "current": {"selected": True, "text": "grafanacloud-stephenwagner-logs", "value": "grafanacloud-logs"},
                "hide": 0, "skipUrlSync": False, "includeAll": False, "multi": False, "options": [],
            },
        ],
    },
    "annotations": {
        "list": [
            {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
             "enable": True, "hide": True, "name": "Annotations & Alerts", "type": "dashboard",
             "iconColor": "rgba(0, 211, 255, 1)"},
            {
                "datasource": PROM_DS,
                "enable": True, "hide": False,
                "iconColor": PURPLE,
                "name": "Spillover events",
                "expr": "increase(llm_gateway_spillover_total[1m]) > 0",
                "step": "1m",
                "titleFormat": "Ollama→Claude spillover",
                "useValueForTime": False,
            },
        ],
    },
    "panels": panels,
}

DASH.write_text(json.dumps(dashboard, indent=2))
print(f"Wrote {DASH} — {len(panels)} panels")
