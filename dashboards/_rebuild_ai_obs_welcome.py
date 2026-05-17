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

Premium design system (v2): slate-950 canvas, slate-900 cards, sky-400 signature
color for the AI moment, gradient borders via mask-composite, Geist + Inter +
JetBrains Mono typography.
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
    accepts "markdown" and "html". For the v2 premium design system all text
    panels use mode="html" to guarantee the inline styles and gradient borders
    render correctly.
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

    Uses thresholds-mode coloring. The base step (noValue) is slate-500
    (#64748B) so empty panels render muted gray, not danger red. Caller can
    pass `thresholds` to override the full step list.
    """
    threshold_steps = thresholds or [
        {"color": "#64748B", "value": None},
        {"color": color, "value": 0},
    ]
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

# Font import line used at the top of every text panel (so styles work even
# if Grafana's text plugin doesn't cache the @import across panels).
FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Geist:wght@400;600;700;800&"
    "family=Inter:wght@400;500;600&"
    "family=JetBrains+Mono:wght@500;600&display=swap');"
)


WELCOME_TITLE_HTML = f"""<style>
{FONT_IMPORT}
.hero-wrap{{position:relative;font-family:'Geist',Inter,system-ui,sans-serif;padding:48px 40px 56px;text-align:center;color:#F8FAFC;background:radial-gradient(120% 100% at 50% 0%,rgba(56,189,248,0.10) 0%,rgba(2,6,23,0) 60%),linear-gradient(180deg,#0F172A 0%,#020617 100%);border-radius:16px;overflow:hidden;}}
.hero-wrap::before{{content:'';position:absolute;inset:0;border-radius:16px;padding:1px;background:linear-gradient(135deg,rgba(56,189,248,0.45),rgba(167,139,250,0.35));-webkit-mask:linear-gradient(#000,#000) content-box,linear-gradient(#000,#000);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;}}
.hero-eyebrow{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:11px;letter-spacing:0.24em;color:#38BDF8;text-transform:uppercase;margin-bottom:14px;}}
.hero-title{{font-size:54px;font-weight:800;letter-spacing:-0.025em;line-height:1.05;margin:0;text-shadow:0 0 36px rgba(56,189,248,0.25);}}
.hero-title .ai{{background:linear-gradient(135deg,#38BDF8 0%,#A78BFA 100%);-webkit-background-clip:text;background-clip:text;color:transparent;}}
.hero-sub{{font-family:Inter,system-ui,sans-serif;font-size:18px;font-weight:400;color:#94A3B8;margin:14px 0 28px;}}
.hero-rule{{width:120px;height:2px;margin:0 auto;background:linear-gradient(90deg,#38BDF8,#F472B6);border-radius:1px;box-shadow:0 0 12px rgba(56,189,248,0.5);}}
@keyframes shimmer{{0%,100%{{opacity:0.65}}50%{{opacity:1}}}}
.hero-rule{{animation:shimmer 4s ease-in-out infinite;}}
</style>
<div class="hero-wrap">
  <div class="hero-eyebrow">Grafana Labs. Observability for AI.</div>
  <h1 class="hero-title"><span class="ai">AI Observability</span><br/>with Grafana Labs</h1>
  <p class="hero-sub">Where conversations join the OTel stack.</p>
  <div class="hero-rule"></div>
</div>
"""


THESIS_HTML = f"""<style>
{FONT_IMPORT}
.thesis-card{{position:relative;font-family:'Geist',Inter,system-ui,sans-serif;padding:32px 36px;background:linear-gradient(180deg,rgba(15,23,42,0.6) 0%,rgba(2,6,23,0.4) 100%);border-radius:14px;color:#F8FAFC;display:flex;align-items:center;gap:24px;}}
.thesis-card::before{{content:'';position:absolute;left:0;top:24px;bottom:24px;width:4px;border-radius:2px;background:linear-gradient(180deg,#38BDF8,#A78BFA);box-shadow:0 0 18px rgba(56,189,248,0.45);}}
.thesis-eyebrow{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10px;letter-spacing:0.22em;color:#38BDF8;text-transform:uppercase;}}
.thesis-text{{font-size:22px;font-weight:500;line-height:1.45;letter-spacing:-0.01em;color:#E2E8F0;margin:8px 0 0;}}
.thesis-text .now{{color:#38BDF8;font-weight:700;}}
</style>
<div class="thesis-card">
  <div>
    <div class="thesis-eyebrow">The Thesis</div>
    <p class="thesis-text">AI changed the time to value of observability. <span class="now">Now observability changes the time to value of AI.</span></p>
  </div>
</div>
"""


def spectrum_html(left_label, right_label, ai_pct, eng_pct):
    """v2 spectrum card. Gradient track, two position markers (orange AI on
    left side, sky Engineering on right side), tick marks at 25/50/75%.
    """
    return f"""<style>
{FONT_IMPORT}
.spec-card{{font-family:Inter,system-ui,sans-serif;padding:22px 24px 26px;background:linear-gradient(180deg,#0F172A 0%,#0B1220 100%);border-radius:12px;position:relative;color:#F8FAFC;}}
.spec-card::after{{content:'';position:absolute;inset:0;border-radius:12px;padding:1px;background:linear-gradient(135deg,rgba(56,189,248,0.30),rgba(167,139,250,0.20));-webkit-mask:linear-gradient(#000,#000) content-box,linear-gradient(#000,#000);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;}}
.spec-head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:18px;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10px;letter-spacing:0.18em;text-transform:uppercase;}}
.spec-head .left{{color:#FB923C;}}
.spec-head .right{{color:#38BDF8;}}
.spec-track{{position:relative;height:28px;border-radius:8px;background:linear-gradient(90deg,#FB923C 0%,#F472B6 33%,#A78BFA 66%,#38BDF8 100%);box-shadow:inset 0 0 0 1px rgba(255,255,255,0.06),0 4px 18px rgba(56,189,248,0.15);}}
.spec-track .tick{{position:absolute;top:-4px;width:1px;height:36px;background:rgba(255,255,255,0.16);}}
.spec-track .tick.t25{{left:25%;}}.spec-track .tick.t50{{left:50%;}}.spec-track .tick.t75{{left:75%;}}
.spec-marker{{position:absolute;top:-9px;width:12px;height:12px;border-radius:50%;background:#F8FAFC;box-shadow:0 0 0 3px #0F172A,0 0 14px rgba(255,255,255,0.6);transform:translateX(-50%);}}
.spec-marker.eng{{background:#38BDF8;box-shadow:0 0 0 3px #0F172A,0 0 16px rgba(56,189,248,0.8);}}
.spec-marker .lbl{{position:absolute;top:-22px;left:50%;transform:translateX(-50%);font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:0.14em;color:#F8FAFC;white-space:nowrap;text-transform:uppercase;}}
</style>
<div class="spec-card">
  <div class="spec-head"><span class="left">{left_label}</span><span class="right">{right_label}</span></div>
  <div class="spec-track">
    <span class="tick t25"></span><span class="tick t50"></span><span class="tick t75"></span>
    <span class="spec-marker eng" style="left:{eng_pct}%"><span class="lbl">Engineering</span></span>
    <span class="spec-marker ai" style="left:{ai_pct}%"><span class="lbl">AI today</span></span>
  </div>
</div>
"""


SIGNAL_STACK_HTML = f"""<style>
{FONT_IMPORT}
.sig-wrap{{font-family:'Geist',Inter,system-ui,sans-serif;padding:32px 40px;background:linear-gradient(180deg,#0F172A 0%,#0B1220 100%);border-radius:14px;color:#F8FAFC;position:relative;}}
.sig-wrap::after{{content:'';position:absolute;inset:0;border-radius:14px;padding:1px;background:linear-gradient(135deg,rgba(56,189,248,0.30),rgba(167,139,250,0.20));-webkit-mask:linear-gradient(#000,#000) content-box,linear-gradient(#000,#000);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;}}
.sig-row{{position:relative;display:flex;justify-content:space-between;align-items:center;margin-bottom:32px;padding:0 12px;}}
.sig-row::before{{content:'';position:absolute;top:50%;left:8%;right:8%;height:1px;background:linear-gradient(90deg,rgba(138,184,255,0.4),rgba(167,139,250,0.4),rgba(244,114,182,0.4),rgba(251,146,60,0.4));z-index:0;}}
.sig-node{{position:relative;z-index:1;padding:12px 22px;border-radius:10px;background:#0F172A;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13px;letter-spacing:0.10em;font-weight:600;text-transform:uppercase;}}
.sig-node.metrics{{color:#8AB8FF;box-shadow:0 0 0 1px rgba(138,184,255,0.45),0 0 22px rgba(138,184,255,0.18);}}
.sig-node.logs{{color:#A78BFA;box-shadow:0 0 0 1px rgba(167,139,250,0.45),0 0 22px rgba(167,139,250,0.18);}}
.sig-node.traces{{color:#F472B6;box-shadow:0 0 0 1px rgba(244,114,182,0.55),0 0 24px rgba(244,114,182,0.25);}}
.sig-node.profiles{{color:#FB923C;box-shadow:0 0 0 1px rgba(251,146,60,0.45),0 0 22px rgba(251,146,60,0.18);}}
.sig-branch{{position:relative;display:flex;justify-content:center;}}
.sig-branch::before{{content:'';position:absolute;left:50%;top:-32px;width:2px;height:28px;background:linear-gradient(180deg,rgba(244,114,182,0.5),rgba(56,189,248,0.8));}}
.sig-branch::after{{content:'';position:absolute;left:50%;top:-8px;width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:8px solid #38BDF8;transform:translateX(-50%);}}
.sig-conv{{padding:16px 28px;border-radius:12px;background:linear-gradient(135deg,rgba(56,189,248,0.10),rgba(167,139,250,0.10));font-family:'JetBrains Mono',ui-monospace,monospace;font-size:14px;letter-spacing:0.10em;font-weight:700;text-transform:uppercase;color:#38BDF8;box-shadow:0 0 0 2px rgba(56,189,248,0.55),0 0 40px rgba(56,189,248,0.30);}}
.sig-caption{{margin-top:32px;text-align:center;font-family:Inter,system-ui,sans-serif;font-size:14px;color:#94A3B8;line-height:1.6;}}
.sig-caption .new{{color:#38BDF8;font-weight:600;}}
</style>
<div class="sig-wrap">
  <div class="sig-row">
    <div class="sig-node metrics">Metrics</div>
    <div class="sig-node logs">Logs</div>
    <div class="sig-node traces">Traces</div>
    <div class="sig-node profiles">Profiles</div>
  </div>
  <div class="sig-branch"><div class="sig-conv">Conversations</div></div>
  <div class="sig-caption">Metrics, logs, traces, profiles. The four classical signals of OpenTelemetry. <span class="new">The fifth signal, conversations,</span> branches from traces.</div>
</div>
"""


# Singularity (panel 401): two-column inside the panel. Pull-quote on left,
# vertical ladder on right. Emoji rendered via HTML entity codes so JSON
# serialization is safe (resolves to: speech-balloon, compass, hammer-wrench,
# warning, math-S).
SINGULARITY_HTML = f"""<style>
{FONT_IMPORT}
.walk{{font-family:Inter,system-ui,sans-serif;padding:24px 28px;background:linear-gradient(180deg,#0F172A 0%,#0B1220 100%);border-radius:14px;color:#F8FAFC;position:relative;display:grid;grid-template-columns:1fr auto;gap:32px;align-items:start;}}
.walk::after{{content:'';position:absolute;inset:0;border-radius:14px;padding:1px;background:linear-gradient(135deg,rgba(56,189,248,0.30),rgba(167,139,250,0.20));-webkit-mask:linear-gradient(#000,#000) content-box,linear-gradient(#000,#000);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;}}
.walk-quote{{font-size:16px;line-height:1.6;color:#CBD5E1;border-left:4px solid;border-image:linear-gradient(180deg,#38BDF8,#A78BFA) 1;padding-left:18px;margin:0;}}
.walk-quote .punch{{display:block;margin-top:14px;color:#38BDF8;font-weight:700;font-family:'Geist',Inter,system-ui,sans-serif;font-size:18px;letter-spacing:-0.01em;}}
.walk-ladder{{display:flex;flex-direction:column;gap:6px;min-width:200px;}}
.walk-step{{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:10px;background:#1E293B;border:1px solid rgba(148,163,184,0.10);}}
.walk-step .ico{{width:26px;height:26px;border-radius:6px;display:grid;place-items:center;font-size:14px;}}
.walk-step .lbl{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:11px;letter-spacing:0.10em;text-transform:uppercase;color:#F8FAFC;}}
.walk-step.s1 .ico{{background:rgba(56,189,248,0.15);color:#38BDF8;box-shadow:inset 0 0 0 1px rgba(56,189,248,0.30);}}
.walk-step.s2 .ico{{background:rgba(138,184,255,0.15);color:#8AB8FF;box-shadow:inset 0 0 0 1px rgba(138,184,255,0.30);}}
.walk-step.s3 .ico{{background:rgba(167,139,250,0.15);color:#A78BFA;box-shadow:inset 0 0 0 1px rgba(167,139,250,0.30);}}
.walk-step.s4 .ico{{background:rgba(244,114,182,0.15);color:#F472B6;box-shadow:inset 0 0 0 1px rgba(244,114,182,0.30);}}
.walk-step.s5 .ico{{background:rgba(251,146,60,0.15);color:#FB923C;box-shadow:inset 0 0 0 1px rgba(251,146,60,0.30);}}
.walk-arrow{{display:grid;place-items:center;height:12px;color:#475569;font-size:12px;font-family:'JetBrains Mono',monospace;}}
</style>
<div class="walk">
  <p class="walk-quote">From a conversation, you can walk down to the trace that produced it, the tool the model called, the database it queried, the error on Postgres, and the SQL itself.<span class="punch">Observability is the control plane for AI systems.</span></p>
  <div class="walk-ladder">
    <div class="walk-step s1"><span class="ico">&#128172;</span><span class="lbl">Conversation</span></div>
    <div class="walk-arrow">v</div>
    <div class="walk-step s2"><span class="ico">&#129517;</span><span class="lbl">Trace</span></div>
    <div class="walk-arrow">v</div>
    <div class="walk-step s3"><span class="ico">&#128736;</span><span class="lbl">Tool call</span></div>
    <div class="walk-arrow">v</div>
    <div class="walk-step s4"><span class="ico">&#9888;</span><span class="lbl">DB error</span></div>
    <div class="walk-arrow">v</div>
    <div class="walk-step s5"><span class="ico">&#119826;</span><span class="lbl">SQL</span></div>
  </div>
</div>
"""


INSIGHT_CALLOUT_HTML = f"""<style>
{FONT_IMPORT}
.callout{{font-family:Inter,system-ui,sans-serif;padding:24px 20px;color:#CBD5E1;}}
.callout-eyebrow{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10px;letter-spacing:0.22em;color:#38BDF8;text-transform:uppercase;margin-bottom:18px;}}
.callout-line{{font-size:17px;font-weight:500;line-height:1.5;color:#F8FAFC;margin:0 0 10px;}}
.callout-line.muted{{color:#94A3B8;font-weight:400;font-size:15px;}}
</style>
<div class="callout">
  <div class="callout-eyebrow">What this enables</div>
  <p class="callout-line">One observability stack.</p>
  <p class="callout-line">Five signals.</p>
  <p class="callout-line muted">Every layer of an AI system, queryable from the same place.</p>
</div>
"""


def nav_card_html(num, title, accent, accent_glow):
    """v2 nav card with numbered badge in accent color and gradient border.

    `num` is a string like "01". `accent` is the hex stop, `accent_glow` is the
    rgba shadow companion.
    """
    return f"""<style>
{FONT_IMPORT}
.nav-card{{font-family:Inter,system-ui,sans-serif;padding:22px 20px;background:linear-gradient(180deg,#0F172A 0%,#0B1220 100%);border-radius:12px;color:#F8FAFC;position:relative;overflow:hidden;height:100%;display:flex;flex-direction:column;justify-content:space-between;}}
.nav-card::after{{content:'';position:absolute;inset:0;border-radius:12px;padding:1px;background:linear-gradient(135deg,var(--accent,#38BDF8),rgba(148,163,184,0.10));-webkit-mask:linear-gradient(#000,#000) content-box,linear-gradient(#000,#000);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none;}}
.nav-num{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:32px;font-weight:700;letter-spacing:-0.02em;line-height:1;color:var(--accent,#38BDF8);text-shadow:0 0 18px var(--accent-glow,rgba(56,189,248,0.30));}}
.nav-title{{font-family:'Geist',Inter,system-ui,sans-serif;font-size:16px;font-weight:600;color:#F8FAFC;margin:14px 0 6px;letter-spacing:-0.01em;}}
.nav-sub{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:0.18em;text-transform:uppercase;color:#64748B;}}
</style>
<div class="nav-card" style="--accent:{accent};--accent-glow:{accent_glow};">
  <div class="nav-num">{num}</div>
  <div>
    <div class="nav-title">{title}</div>
    <div class="nav-sub">Brief pending</div>
  </div>
</div>
"""


AXIS_HTML = f"""<style>
{FONT_IMPORT}
.axis-wrap{{font-family:Inter,system-ui,sans-serif;padding:8px 12px 4px;color:#94A3B8;}}
.axis-head{{display:flex;justify-content:space-between;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase;margin-bottom:8px;}}
.axis-head .left{{color:#FB923C;}}.axis-head .right{{color:#38BDF8;}}
.axis-bar{{height:32px;border-radius:8px;background:linear-gradient(90deg,#FB923C 0%,#F472B6 33%,#A78BFA 66%,#38BDF8 100%);box-shadow:inset 0 0 0 1px rgba(255,255,255,0.06),0 6px 24px rgba(56,189,248,0.18);}}
.axis-foot{{text-align:center;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:0.16em;text-transform:uppercase;color:#64748B;margin-top:8px;}}
</style>
<div class="axis-wrap">
  <div class="axis-head"><span class="left">Deterministic. Objective. Production.</span><span class="right">Subjective. Probabilistic. Development.</span></div>
  <div class="axis-bar"></div>
  <div class="axis-foot">Five views move right to left across this axis.</div>
</div>
"""


# ---------- build panels ----------

P = []

# Row 1: Title + thesis (with the ribbon at the top of the dashboard)
P.append(ribbon_panel())  # 100

P.append(text_panel(
    pid=101,
    content=WELCOME_TITLE_HTML,
    x=0, y=3, w=24, h=6,
    transparent=True,
    mode="html",
))

P.append(text_panel(
    pid=102,
    content=THESIS_HTML,
    x=0, y=9, w=24, h=5,
    transparent=True,
    mode="html",
))

# Row 2: The four spectra
P.append(row_panel(
    pid=200,
    title="The four spectra. Engineering loves the right side. AI lives on the left. Observability is the bridge.",
    y=14,
))

# (pid, left_label, right_label, x, ai_pct, eng_pct)
SPECTRA = [
    (201, "Production",      "Development",   0,  18, 82),
    (202, "Customer facing", "Internal",      6,  22, 78),
    (203, "Deterministic",   "Probabilistic", 12, 15, 85),
    (204, "Objective",       "Subjective",    18, 20, 80),
]
for pid, left, right, x, ai_pct, eng_pct in SPECTRA:
    P.append(text_panel(
        pid=pid,
        content=spectrum_html(left, right, ai_pct, eng_pct),
        x=x, y=15, w=6, h=4,
        transparent=False,
        mode="html",
    ))

# Row 3: The fifth signal
P.append(row_panel(
    pid=300,
    title="The fifth signal. Conversations branch from traces. Every conversation is a trace, but not every trace is a conversation.",
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
    title="The singularity. From any conversation, walk down to the SQL that broke.",
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
    content=INSIGHT_CALLOUT_HTML,
    x=16, y=30, w=8, h=8,
    transparent=True,
    title="",
    mode="html",
))

# Row 5: The path ahead
P.append(row_panel(
    pid=500,
    title="The path ahead. Five views, one journey.",
    y=38,
))

# (pid, x, num, title, accent, accent_glow)
NAV_CARDS = [
    (501, 2,  "01", "View one",   "#FB923C", "rgba(251,146,60,0.30)"),
    (502, 6,  "02", "View two",   "#F472B6", "rgba(244,114,182,0.30)"),
    (503, 10, "03", "View three", "#A78BFA", "rgba(167,139,250,0.30)"),
    (504, 14, "04", "View four",  "#8AB8FF", "rgba(138,184,255,0.30)"),
    (505, 18, "05", "View five",  "#38BDF8", "rgba(56,189,248,0.30)"),
]
for pid, x, num, title, accent, glow in NAV_CARDS:
    P.append(text_panel(
        pid=pid,
        content=nav_card_html(num, title, accent, glow),
        x=x, y=39, w=4, h=6,
        transparent=False,
        mode="html",
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
    title="Highlights from the last 24 hours. Live signals from a real AI system.",
    y=47,
))

# Cost expressions: split by token_type with a fallback for the unlabelled case.
ANTHROPIC_EXPR = (
    '(sum(increase(gen_ai_client_token_usage_total{token_type="input"}[24h])) / 1000000 * 3 '
    '+ sum(increase(gen_ai_client_token_usage_total{token_type="output"}[24h])) / 1000000 * 15) '
    'or sum(increase(gen_ai_client_token_usage_total[24h])) / 1000000 * 5.4'
)
LOCAL_COST_EXPR = 'sum(increase(gen_ai_client_token_usage_total[24h])) / 1000000 * 0.20'
SAVINGS_EXPR = (
    '100 * (1 - (' + LOCAL_COST_EXPR + ') / '
    'clamp_min((' + ANTHROPIC_EXPR + '), 0.001))'
)

# 601: Tokens served. unit=short auto-formats 203233030 as "203 Mil".
P.append(stat_panel(
    pid=601,
    title="Tokens served (24h)",
    expr="sum(increase(gen_ai_client_token_usage_total[24h]))",
    x=0, y=48, w=4, h=4,
    unit="short", decimals=0,
    no_value="0",
    color=PALETTE["blue"],
    description="Total LLM tokens (input + output) the platform processed in the trailing 24 hours.",
))

# 602: Cost local marginal. Uses LOCAL_COST_EXPR.
P.append(stat_panel(
    pid=602,
    title="Cost, local marginal",
    expr=LOCAL_COST_EXPR,
    x=4, y=48, w=4, h=4,
    unit="currencyUSD", decimals=2,
    no_value="0",
    color="#38BDF8",
    description="What the on-prem traffic cost over the last 24h at a $0.20/Mtok all-in rate (electricity + amortization).",
))

# 603: Cost equivalent Anthropic. Uses ANTHROPIC_EXPR with token-type split.
P.append(stat_panel(
    pid=603,
    title="Cost, equivalent Anthropic",
    expr=ANTHROPIC_EXPR,
    x=8, y=48, w=4, h=4,
    unit="currencyUSD", decimals=2,
    no_value="0",
    color=PALETTE["purple"],
    description="What the same 24h of token volume would have cost on Anthropic Claude Sonnet ($3/$15 per 1M input/output tokens; falls back to a $5.40/Mtok blend when token_type is absent).",
))

# 604: Savings HERO. Bright sky-blue when >= 90%, never red.
P.append(stat_panel(
    pid=604,
    title="Savings",
    expr=SAVINGS_EXPR,
    x=12, y=48, w=4, h=4,
    unit="percent", decimals=1,
    no_value="...",
    color_mode="background",
    thresholds=[
        {"color": "#64748B", "value": None},   # noValue: muted slate-500
        {"color": "#0EA5E9", "value": 0},      # sub-90%: sky-500
        {"color": "#38BDF8", "value": 90},     # 90%+: bright sky-400 (hero)
    ],
    description="Percent saved by running local vs the equivalent Anthropic cost over the last 24h. 90% or better lights up sky-blue.",
))

# 605: Conversations. unit=short auto-formats large counts.
P.append(stat_panel(
    pid=605,
    title="Conversations (24h)",
    expr="sum(increase(sigil_eval_executions_total[24h]))",
    x=16, y=48, w=4, h=4,
    unit="short", decimals=0,
    no_value="0",
    color=PALETTE["pink"],
    description="Total evaluated conversations in the last 24h, as recorded by the Sigil evaluator pipeline.",
))

# 606: Evaluations passed (%). The Sigil status label uses "success" not
# "pass" on this tenant; query both for portability.
EVAL_PASS_EXPR = (
    "100 * ("
    "sum(increase(sigil_eval_executions_total{status=~\"success|pass\"}[24h])) "
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
    description="Percentage of Sigil evaluator runs in the trailing 24h whose status was success.",
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
# re-flips these three.
NARRATIVE_TRANSPARENT_IDS = {101, 102, 506}

DASH_PATH.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"Wrote {DASH_PATH} with {len(P)} panels.")
print(f"Post-aesthetic TODO: ensure ids {sorted(NARRATIVE_TRANSPARENT_IDS)} have transparent=True.")
