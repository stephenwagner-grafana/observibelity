#!/usr/bin/env python3
"""
Rebuild ai-obs-welcome.json. Archetype: welcome-screen.

This is the opener for an AI observability story presentation. It mirrors the
OOTB Grafana AI Observability landing page (hero block + KPI strip at the
bottom) but adds narrative content cards in between as a PPT-replacement
opener.

Rows, top to bottom:
  1. Title + thesis (hero markdown, ribbon above)
  2. The four spectra (engineering vs AI, four gradient bars)
  3. The fifth signal (MLTPC diagram)
  4. The singularity (conversation -> trace -> tool -> DB -> SQL walk + callout)
  5. The path ahead (five nav cards + axis)
  6. Last-24h KPI strip (six stat panels, savings hero)

TODO: populate nav cards 501-505 with real child dashboard titles + links once
the 5 views are briefed.
"""
import json
from pathlib import Path
import sys

# Allow direct import of design tokens from this folder.
sys.path.insert(0, str(Path(__file__).parent))
from _design_tokens import PALETTE, STATUS, STANDARD_VARS  # noqa: E402

DASH_PATH = Path(__file__).parent / "ai-obs-welcome.json"

PROM_DS = {"type": "prometheus", "uid": "${datasource_prom}"}

# ---------- grid helpers ----------

def gp(x, y, w, h):
    return {"h": h, "w": w, "x": x, "y": y}


# ---------- panel factories ----------

def ribbon_panel():
    """Same transparent ribbon shape produced by the aesthetic pass.
    Included explicitly so the rebuild produces a complete dashboard on its
    own; the aesthetic pass is idempotent and will leave this in place.
    """
    return {
        "id": 100,
        "type": "timeseries",
        "title": "",
        "description": "",
        "transparent": True,
        "gridPos": gp(0, 0, 24, 3),
        "datasource": PROM_DS,
        "targets": [{
            "datasource": PROM_DS,
            "expr": "sum(rate(gen_ai_client_token_usage_total[$__rate_interval])) * 60",
            "legendFormat": "tokens/min",
            "range": True,
            "refId": "A",
        }],
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "custom": {
                    "drawStyle": "bars",
                    "barAlignment": 0,
                    "barWidthFactor": 0.92,
                    "fillOpacity": 100,
                    "gradientMode": "scheme",
                    "lineWidth": 0,
                    "axisPlacement": "hidden",
                    "axisLabel": "",
                    "axisColorMode": "text",
                    "showPoints": "never",
                    "spanNulls": False,
                    "hideFrom": {"legend": True, "tooltip": False, "viz": False},
                    "stacking": {"group": "A", "mode": "none"},
                    "thresholdsStyle": {"mode": "off"},
                },
                "thresholds": {
                    "mode": "percentage",
                    "steps": [
                        {"color": PALETTE["blue"],   "value": None},
                        {"color": PALETTE["purple"], "value": 30},
                        {"color": PALETTE["pink"],   "value": 65},
                        {"color": PALETTE["orange"], "value": 88},
                    ],
                },
                "unit": "short",
            },
            "overrides": [],
        },
        "options": {
            "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "single", "sort": "none"},
        },
    }


def text_panel(*, pid, content, x, y, w, h, title="", transparent=True, mode="markdown"):
    """Markdown or HTML text panel.

    `mode` controls how Grafana renders the content. Grafana's text panel
    accepts "markdown" and "html". Inline HTML inside a markdown panel
    generally renders, but for the spectrum / signal-stack / singularity /
    axis blocks we use mode="html" to guarantee the inline styles render.
    """
    return {
        "id": pid,
        "type": "text",
        "title": title,
        "transparent": transparent,
        "gridPos": gp(x, y, w, h),
        "options": {
            "mode": mode,
            "code": {
                "language": "plaintext",
                "showLineNumbers": False,
                "showMiniMap": False,
            },
            "content": content,
        },
    }


def row_panel(*, pid, title, y):
    return {
        "id": pid,
        "type": "row",
        "title": title,
        "gridPos": gp(0, y, 24, 1),
        "collapsed": False,
        "panels": [],
    }


def stat_panel(*, pid, title, expr, x, y, w, h, unit="none", custom_unit=None,
               decimals=0, no_value="0", color="#8AB8FF", color_mode="value",
               thresholds=None, graph="area", description=""):
    """Standard KPI-strip stat panel.

    Uses thresholds-mode coloring so single-step thresholds give a flat fill
    of the desired palette color. `instant=True` keeps the panel stable
    between refreshes (no range-query flicker).
    """
    # Use Grafana's standard customUnit field per design system §2.5 so the
    # text renders cleanly after the value. A range query (instant=False)
    # gives the aesthetic pass enough time series to render the sparkline;
    # noValue handles the warmup window.
    threshold_steps = thresholds or [{"color": color, "value": None}]
    defaults = {
        "unit": unit,
        "decimals": decimals,
        "noValue": no_value,
        "color": {"mode": "thresholds"},
        "thresholds": {"mode": "absolute", "steps": threshold_steps},
    }
    if custom_unit is not None:
        defaults["custom"] = {"customUnit": custom_unit}
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "description": description,
        "gridPos": gp(x, y, w, h),
        "datasource": PROM_DS,
        "targets": [{
            "datasource": PROM_DS,
            "refId": "A",
            "expr": expr,
            "legendFormat": "",
            "instant": False,
            "range": True,
        }],
        "fieldConfig": {
            "defaults": defaults,
            "overrides": [],
        },
        "options": {
            "colorMode": color_mode,
            "graphMode": graph,
            "justifyMode": "center",
            "orientation": "auto",
            "percentChangeColorMode": "inverted",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showPercentChange": False,
            "textMode": "auto",
            "wideLayout": False,
        },
    }


# ---------- content blocks ----------

WELCOME_TITLE_MD = """<div style="text-align: center; padding: 1rem;">

# AI Observability with Grafana Labs

### Where conversations join the OTel stack

</div>
"""

# Note: no em dashes anywhere. Sentences separated by periods.
THESIS_MD = """<div style="text-align: center; font-size: 1.3em; padding: 1rem; color: #cbd5e1;">

AI changed the time-to-value of observability.
Now observability changes the time-to-value of AI.

</div>
"""


def spectrum_html(left_label, right_label):
    return (
        '<div style="padding: 0.5rem;">\n'
        '  <div style="display: flex; justify-content: space-between; '
        'font-size: 0.85em; color: #9ca3af; margin-bottom: 0.4rem;">\n'
        f'    <span>{left_label}</span>\n'
        f'    <span>{right_label}</span>\n'
        '  </div>\n'
        '  <div style="height: 12px; border-radius: 6px; '
        'background: linear-gradient(90deg, #8AB8FF 0%, #A78BFA 33%, '
        '#F472B6 66%, #FB923C 100%);"></div>\n'
        '</div>\n'
    )


SIGNAL_STACK_HTML = """<div style="padding: 1.5rem; text-align: center; font-family: monospace;">

<div style="display: flex; justify-content: space-around; margin-bottom: 1rem;">
  <span style="padding: 0.5rem 1rem; border-radius: 4px; background: rgba(138, 184, 255, 0.15); color: #8AB8FF; border: 1px solid #8AB8FF;">Metrics</span>
  <span style="padding: 0.5rem 1rem; border-radius: 4px; background: rgba(167, 139, 250, 0.15); color: #A78BFA; border: 1px solid #A78BFA;">Logs</span>
  <span style="padding: 0.5rem 1rem; border-radius: 4px; background: rgba(244, 114, 182, 0.15); color: #F472B6; border: 1px solid #F472B6;">Traces</span>
  <span style="padding: 0.5rem 1rem; border-radius: 4px; background: rgba(251, 146, 60, 0.15); color: #FB923C; border: 1px solid #FB923C;">Profiles</span>
</div>

<div style="font-size: 2em; color: #F472B6; margin: 0.5rem 0;">&darr;</div>

<div>
  <span style="padding: 0.6rem 1.2rem; border-radius: 6px; background: rgba(252, 165, 165, 0.2); color: #FCA5A5; border: 2px solid #FCA5A5; font-weight: bold;">Conversations</span>
</div>

<p style="color: #9ca3af; font-size: 0.9em; margin-top: 1.5rem; max-width: 700px; margin-left: auto; margin-right: auto;">
Metrics, logs, traces, profiles. The four classical signals of OpenTelemetry. The fifth signal, conversations, branches from traces.
</p>

</div>
"""


SINGULARITY_HTML = """<div style="padding: 1rem;">

<p style="font-size: 1.1em; color: #e2e8f0; line-height: 1.6;">
From a conversation, you can walk down to the trace that produced it, the tool the model called, the database it queried, the error on Postgres, and the SQL itself.
</p>

<p style="font-size: 1.1em; color: #f9a8d4; line-height: 1.6; font-weight: 500;">
Observability is the control plane for AI systems.
</p>

<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; font-family: monospace; font-size: 0.9em;">
  <span style="padding: 0.4rem 0.8rem; border-radius: 4px; background: rgba(103, 232, 249, 0.15); color: #67E8F9; border: 1px solid #67E8F9;">Conversation</span>
  <span style="color: #64748b;">&rarr;</span>
  <span style="padding: 0.4rem 0.8rem; border-radius: 4px; background: rgba(138, 184, 255, 0.15); color: #8AB8FF; border: 1px solid #8AB8FF;">Trace</span>
  <span style="color: #64748b;">&rarr;</span>
  <span style="padding: 0.4rem 0.8rem; border-radius: 4px; background: rgba(167, 139, 250, 0.15); color: #A78BFA; border: 1px solid #A78BFA;">Tool call</span>
  <span style="color: #64748b;">&rarr;</span>
  <span style="padding: 0.4rem 0.8rem; border-radius: 4px; background: rgba(244, 114, 182, 0.15); color: #F472B6; border: 1px solid #F472B6;">DB error</span>
  <span style="color: #64748b;">&rarr;</span>
  <span style="padding: 0.4rem 0.8rem; border-radius: 4px; background: rgba(251, 146, 60, 0.15); color: #FB923C; border: 1px solid #FB923C;">SQL</span>
</div>

</div>
"""


INSIGHT_CALLOUT_MD = """<div style="padding: 1rem; font-size: 0.95em; color: #cbd5e1; line-height: 1.6;">

One observability stack.
Five signals.
Every layer of an AI system, queryable from the same place.

</div>
"""


def nav_card_md(n):
    return (
        '<div style="padding: 1rem; text-align: center;">\n\n'
        f"### View {n}\n\n"
        '<p style="color: #9ca3af; font-size: 0.85em;">\n'
        "(brief pending)\n"
        "</p>\n\n"
        "</div>\n"
    )


AXIS_HTML = """<div style="padding: 0 0.5rem;">
  <div style="display: flex; justify-content: space-between; font-size: 0.85em; color: #9ca3af; margin-bottom: 0.4rem;">
    <span>Deterministic. Objective. Production. Customer facing.</span>
    <span>Subjective. Probabilistic. Development. Internal.</span>
  </div>
  <div style="height: 10px; border-radius: 5px; background: linear-gradient(90deg, #FB923C 0%, #F472B6 33%, #A78BFA 66%, #8AB8FF 100%);"></div>
  <p style="text-align: center; font-size: 0.8em; color: #64748b; margin-top: 0.3rem;">Five views move right to left across this axis.</p>
</div>
"""


# ---------- build panels ----------

P = []

# Row 1: Title + thesis (with the ribbon at the top of the dashboard)
P.append(ribbon_panel())  # 100

P.append(text_panel(
    pid=101,
    content=WELCOME_TITLE_MD,
    x=0, y=3, w=24, h=6,
    transparent=True,
    mode="markdown",
))

P.append(text_panel(
    pid=102,
    content=THESIS_MD,
    x=0, y=9, w=24, h=5,
    transparent=True,
    mode="markdown",
))

# Row 2: The four spectra
P.append(row_panel(
    pid=200,
    title="🧭 The four spectra. Engineering loves the right side. AI lives on the left. Observability is the bridge.",
    y=14,
))

SPECTRA = [
    (201, "Production",      "Development",   0),
    (202, "Customer facing", "Internal",      6),
    (203, "Deterministic",   "Probabilistic", 12),
    (204, "Objective",       "Subjective",    18),
]
for pid, left, right, x in SPECTRA:
    P.append(text_panel(
        pid=pid,
        content=spectrum_html(left, right),
        x=x, y=15, w=6, h=4,
        transparent=True,
        mode="html",
    ))

# Row 3: The fifth signal
P.append(row_panel(
    pid=300,
    title="🔭 The fifth signal. Conversations branch from traces. Every conversation is a trace, but not every trace is a conversation.",
    y=19,
))

P.append(text_panel(
    pid=301,
    content=SIGNAL_STACK_HTML,
    x=0, y=20, w=24, h=9,
    transparent=False,
    mode="html",
))

# Row 4: The singularity
P.append(row_panel(
    pid=400,
    title="🧶 The singularity. From any conversation, walk down to the SQL that broke.",
    y=29,
))

P.append(text_panel(
    pid=401,
    content=SINGULARITY_HTML,
    x=0, y=30, w=16, h=8,
    transparent=False,
    mode="html",
))

P.append(text_panel(
    pid=402,
    content=INSIGHT_CALLOUT_MD,
    x=16, y=30, w=8, h=8,
    transparent=True,
    title="What this enables",
    mode="markdown",
))

# Row 5: The path ahead
P.append(row_panel(
    pid=500,
    title="🗺 The path ahead. Five views, one journey.",
    y=38,
))

# Five nav cards. Spec puts them at x=2,6,10,14,18 (2-col gutter on each side).
for idx, x in enumerate([2, 6, 10, 14, 18], start=1):
    pid = 500 + idx
    P.append(text_panel(
        pid=pid,
        content=nav_card_md(idx),
        x=x, y=39, w=4, h=6,
        transparent=False,
        mode="markdown",
    ))

P.append(text_panel(
    pid=506,
    content=AXIS_HTML,
    x=0, y=45, w=24, h=2,
    transparent=True,
    mode="html",
))

# Row 6: Highlights from the last 24 hours
P.append(row_panel(
    pid=600,
    title="📊 Highlights from the last 24 hours. Live signals from a real AI system.",
    y=47,
))

# 601: Tokens served
P.append(stat_panel(
    pid=601,
    title="Tokens served (24h)",
    expr="sum(increase(gen_ai_client_token_usage_total[24h]))",
    x=0, y=48, w=4, h=4,
    unit="none", custom_unit=" tokens", decimals=0,
    no_value="0",
    color=PALETTE["blue"],
    description="Total LLM tokens (input + output) the platform processed in the trailing 24 hours.",
))

# 602: Cost local marginal
P.append(stat_panel(
    pid=602,
    title="Cost, local marginal",
    expr='sum(increase(gen_ai_client_cost_usd_total{gen_ai_system="ollama"}[24h]))',
    x=4, y=48, w=4, h=4,
    unit="currencyUSD", decimals=2,
    no_value="0",
    color=PALETTE["cyan"],
    description="What the on-prem Ollama traffic cost over the last 24h (electricity + amortization, per the local cost model).",
))

# 603: Cost equivalent Anthropic
P.append(stat_panel(
    pid=603,
    title="Cost, equivalent Anthropic",
    expr=(
        'sum(increase(gen_ai_client_token_usage_total{token_type="output"}[24h])) * 0.000015 '
        '+ sum(increase(gen_ai_client_token_usage_total{token_type="input"}[24h])) * 0.000003'
    ),
    x=8, y=48, w=4, h=4,
    unit="currencyUSD", decimals=2,
    no_value="0",
    color=PALETTE["purple"],
    description="What the same 24h of token volume would have cost on Anthropic Claude Sonnet (priced at $3 / $15 per 1M input/output tokens).",
))

# 604: Savings HERO. Pure status palette (danger -> warning -> healthy).
# PromQL clamp_min IS supported on this tenant (the LogQL-only rule does not
# apply to Prometheus).
SAVINGS_EXPR = (
    "100 * (1 - ("
    'sum(increase(gen_ai_client_cost_usd_total{gen_ai_system="ollama"}[24h])) '
    "/ clamp_min("
    '(sum(increase(gen_ai_client_token_usage_total{token_type="output"}[24h])) * 0.000015 '
    '+ sum(increase(gen_ai_client_token_usage_total{token_type="input"}[24h])) * 0.000003)'
    ", 0.001)"
    "))"
)
P.append(stat_panel(
    pid=604,
    title="Savings",
    expr=SAVINGS_EXPR,
    x=12, y=48, w=4, h=4,
    unit="percent", decimals=1,
    no_value="...",
    color_mode="background",
    thresholds=[
        {"color": STATUS["danger"],  "value": None},
        {"color": STATUS["warning"], "value": 50},
        {"color": STATUS["healthy"], "value": 90},
    ],
    description="Percent saved by running local marginal Ollama vs the equivalent Anthropic cost. 90% or better is healthy.",
))

# 605: Conversations (24h)
P.append(stat_panel(
    pid=605,
    title="Conversations (24h)",
    expr="sum(increase(sigil_eval_executions_total[24h]))",
    x=16, y=48, w=4, h=4,
    unit="none", custom_unit=" conversations", decimals=0,
    no_value="0",
    color=PALETTE["pink"],
    description="Total evaluated conversations in the last 24h, as recorded by the Sigil evaluator pipeline.",
))

# 606: Evaluations passed (%)
EVAL_PASS_EXPR = (
    "100 * ("
    'sum(increase(sigil_eval_executions_total{status="pass"}[24h])) '
    "/ clamp_min(sum(increase(sigil_eval_executions_total[24h])), 1)"
    ")"
)
P.append(stat_panel(
    pid=606,
    title="Evaluations passed (24h)",
    expr=EVAL_PASS_EXPR,
    x=20, y=48, w=4, h=4,
    unit="percent", decimals=1,
    no_value="0",
    color=PALETTE["mint"],
    description="Percentage of Sigil evaluator runs in the trailing 24h that returned status=pass.",
))


# ---------- assemble dashboard ----------

dashboard = {
    "annotations": {"list": [
        {
            "builtIn": 1,
            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True,
            "hide": True,
            "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts",
            "type": "dashboard",
        },
    ]},
    "description": (
        "Opening welcome screen for the AI observability story. Hero title, "
        "the four spectra, the fifth signal (conversations), the singularity "
        "(conversation walks down to SQL), five nav cards for the journey, "
        "and a live 24h KPI strip."
    ),
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "links": [
        {
            "asDropdown": False,
            "icon": "external link",
            "includeVars": True,
            "keepTime": True,
            "tags": ["observibelity"],
            "title": "AI Observability dashboards",
            "type": "dashboards",
        },
    ],
    "liveNow": False,
    "panels": P,
    "refresh": "30s",
    "schemaVersion": 42,
    "tags": ["ai-observability", "welcome", "observibelity"],
    "templating": {"list": list(STANDARD_VARS)},
    "time": {"from": "now-24h", "to": "now"},
    "timepicker": {
        "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"],
    },
    "timezone": "browser",
    "title": "AI Observability with Grafana Labs",
    "uid": "ai-obs-welcome",
    "version": 0,
    "weekStart": "",
    "folderUid": "obs-ai-observability",
}

# The aesthetic pass flips transparent=True back to False on every non-ribbon
# panel (it treats them as elevated cards). For the welcome-screen archetype,
# the title, the thesis, and the gradient axis should read as PAGE TEXT, not
# as elevated cards. Mark them with a sentinel that survives the aesthetic
# pass: set transparent=True AND tag the panel with a custom field the
# aesthetic pass cannot see. The post-aesthetic step in the build pipeline
# (see _rebuild_ai_obs_welcome_post.sh or the docs) re-flips these three.
NARRATIVE_TRANSPARENT_IDS = {101, 102, 506}

DASH_PATH.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"Wrote {DASH_PATH} with {len(P)} panels.")
print(f"Post-aesthetic TODO: ensure ids {sorted(NARRATIVE_TRANSPARENT_IDS)} have transparent=True.")
