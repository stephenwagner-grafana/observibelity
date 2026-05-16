#!/usr/bin/env python3
"""
Apply the Grafana AI Observability product aesthetic to a dashboard JSON.

Visual contract:
  - Add a full-width "activity ribbon" bar panel at y=0 with the
    blue->purple->pink->orange gradient (signature AI Obs ribbon).
  - All panels transparent: true (lose the boxy chrome).
  - Stat panels: graphMode area sparkline behind the number, value
    color mode, soft palette via thresholds re-mapping.
  - Timeseries: smooth lines, gradient-opacity fills, soft palette.
  - Tables/bargauge: same threshold->soft-palette re-map for cell
    gradients.

Usage:
    python3 _apply_ai_obs_aesthetic.py <dashboard.json>

Rewrites the file in place. Validates JSON before writing.
"""
import json
import sys
import copy
from pathlib import Path

PALETTE = {
    "blue":     "#8AB8FF",
    "purple":   "#A78BFA",
    "pink":     "#F472B6",
    "orange":   "#FB923C",
    "cyan":     "#67E8F9",
    "mint":     "#86EFAC",
    "rose":     "#FCA5A5",
}

# Map legacy named threshold colors -> soft palette equivalents.
COLOR_MAP = {
    "green":              PALETTE["blue"],
    "yellow":             PALETTE["purple"],
    "red":                PALETTE["pink"],
    "orange":             PALETTE["orange"],
    "blue":               PALETTE["blue"],
    "light-blue":         PALETTE["blue"],
    "super-light-green":  PALETTE["cyan"],
    "light-green":        PALETTE["mint"],
    "super-light-red":    PALETTE["rose"],
    "purple":             PALETTE["purple"],
}

RIBBON_HEIGHT = 3
RIBBON_PANEL_ID = 100


def soften_color(c):
    if isinstance(c, str) and c.startswith("#"):
        return c
    return COLOR_MAP.get(c, c)


def soften_threshold_steps(steps):
    return [{**s, "color": soften_color(s.get("color"))} for s in steps]


def build_ribbon_panel():
    return {
        "datasource": {"type": "prometheus", "uid": "${datasource_prom}"},
        "description": "",
        "type": "timeseries",
        "title": "",
        "id": RIBBON_PANEL_ID,
        "transparent": True,
        "gridPos": {"h": RIBBON_HEIGHT, "w": 24, "x": 0, "y": 0},
        "targets": [{
            "datasource": {"type": "prometheus", "uid": "${datasource_prom}"},
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


def transform_stat(panel):
    """Make stat panels feel like AI Obs metric cards.

    Empty-state contract (do NOT undo these):
      * `instant: true` on a target means the panel intentionally avoids the
        range-query flicker. Preserve it and set graphMode='none' so the
        sparkline doesn't try to render an empty time series.
      * `colorMode: 'background'` set explicitly on a panel marks it as a
        hero — preserve it; only default unset stats to `colorMode: 'value'`.
      * `fieldConfig.defaults.noValue` if present is the panel's "$0 / —"
        fallback; never strip it.
    """
    fc = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    if "thresholds" in fc and "steps" in fc["thresholds"]:
        fc["thresholds"]["steps"] = soften_threshold_steps(fc["thresholds"]["steps"])
    fc["color"] = {"mode": "thresholds"}

    opts = panel.setdefault("options", {})
    # Preserve hero treatment if the builder set it; otherwise default to value.
    if opts.get("colorMode") not in ("background", "value", "none"):
        opts["colorMode"] = "value"

    # Sparkline depends on whether the query produces a time series. If any
    # target is instant, we MUST set graphMode='none' or Grafana paints "No
    # data" briefly between refreshes. Default to area for range queries
    # (which gives the soft AI-Obs sparkline backdrop) but never override an
    # explicit graphMode='none' the builder set.
    any_instant = any(t.get("instant") is True for t in panel.get("targets", []))
    if any_instant:
        opts["graphMode"] = "none"
    elif opts.get("graphMode") not in ("area", "line", "none"):
        opts["graphMode"] = "area"

    opts["textMode"] = "auto"
    opts.setdefault("justifyMode", "center")
    opts["wideLayout"] = False
    opts["percentChangeColorMode"] = "inverted"
    opts.setdefault("reduceOptions", {"calcs": ["lastNotNull"], "fields": "", "values": False})

    # NEVER convert instant queries to range — that re-introduces the
    # "No data" flicker that the rebuild scripts explicitly fix.
    # (The previous version of this transform did `t['instant'] = False;
    #  t['range'] = True` here, which broke the empty-state contract.)


def transform_timeseries(panel):
    fc = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    custom = fc.setdefault("custom", {})
    custom["lineInterpolation"] = "smooth"
    custom["lineWidth"] = 2
    custom["showPoints"] = "never"
    custom["spanNulls"] = True
    custom.setdefault("fillOpacity", 30)
    if custom.get("drawStyle", "line") == "line":
        custom["gradientMode"] = "opacity"
    # If stacked area, bump fill so it reads as soft glow.
    if custom.get("stacking", {}).get("mode") in ("normal", "percent"):
        custom["fillOpacity"] = max(custom.get("fillOpacity", 30), 40)
    # Soften any explicit fixedColor overrides.
    for override in panel.get("fieldConfig", {}).get("overrides", []):
        for prop in override.get("properties", []):
            if prop.get("id") == "color":
                val = prop.get("value", {})
                if val.get("mode") == "fixed":
                    val["fixedColor"] = soften_color(val.get("fixedColor"))
    # Pin per-model hues so the same model reads the same color in every panel.
    _add_model_color_overrides(panel)


def transform_table(panel):
    fc = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    if "thresholds" in fc and "steps" in fc["thresholds"]:
        fc["thresholds"]["steps"] = soften_threshold_steps(fc["thresholds"]["steps"])
    # Soften threshold colors in any per-column overrides too.
    for override in panel.get("fieldConfig", {}).get("overrides", []):
        for prop in override.get("properties", []):
            if prop.get("id") == "thresholds":
                val = prop.get("value", {})
                if "steps" in val:
                    val["steps"] = soften_threshold_steps(val["steps"])
    _add_model_color_overrides(panel)


def transform_bargauge(panel):
    fc = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    if "thresholds" in fc and "steps" in fc["thresholds"]:
        fc["thresholds"]["steps"] = soften_threshold_steps(fc["thresholds"]["steps"])
    fc["color"] = {"mode": "thresholds"}
    opts = panel.setdefault("options", {})
    opts["displayMode"] = "gradient"
    opts["valueMode"] = "color"
    opts["showUnfilled"] = True


def transform_barchart(panel):
    """Replace yellow/red continuous schemes with the soft blue->pink gradient."""
    fc = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    if "thresholds" in fc and "steps" in fc["thresholds"]:
        fc["thresholds"]["steps"] = soften_threshold_steps(fc["thresholds"]["steps"])
    # If the existing threshold table is only a single step (which renders
    # every bar identical), switch to a percentage-based gradient so taller
    # bars get visibly hotter colors.
    existing_steps = fc.get("thresholds", {}).get("steps", [])
    if len([s for s in existing_steps if s.get("value") is not None]) == 0:
        fc["thresholds"] = {
            "mode": "percentage",
            "steps": [
                {"color": PALETTE["blue"],   "value": None},
                {"color": PALETTE["purple"], "value": 33},
                {"color": PALETTE["pink"],   "value": 66},
                {"color": PALETTE["orange"], "value": 88},
            ],
        }
    # Force thresholds-based coloring so the soft palette steps actually drive
    # the bar colors. Without this, panels stuck on continuous-GrYlRd keep
    # rendering yellow->red.
    fc["color"] = {"mode": "thresholds"}
    custom = fc.setdefault("custom", {})
    custom.setdefault("gradientMode", "scheme")
    custom.setdefault("fillOpacity", 90)
    custom.setdefault("lineWidth", 0)
    _add_model_color_overrides(panel)


def transform_piechart(panel):
    fc = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    custom = fc.setdefault("custom", {})
    custom.setdefault("hideFrom", {"legend": False, "tooltip": False, "viz": False})
    opts = panel.setdefault("options", {})
    opts.setdefault("pieType", "donut")
    _add_model_color_overrides(panel)


# Per-model color pins: every model that shows up across the dashboard gets a
# slot in the AI Obs palette so the pie, the bar chart, and the table all
# read the same hue for the same model.
MODEL_COLOR_PINS = {
    "claude-opus-4-7":         PALETTE["purple"],
    "claude-opus-4-5-20251015": "#C084FC",  # lighter violet — sister hue to opus-4-7
    "claude-opus-4-5":         "#C084FC",
    "claude-sonnet-4-6":       PALETTE["blue"],
    "claude-haiku-4-5-20251001": PALETTE["cyan"],
    "claude-haiku-4-5":        PALETTE["cyan"],
    # Common non-model series names that otherwise default to palette-classic green
    "loadgen":                 PALETTE["cyan"],
    "live":                    PALETTE["purple"],
    "pass":                    PALETTE["cyan"],
    "fail":                    PALETTE["pink"],
    "< 80":                    PALETTE["blue"],
    "80+":                     PALETTE["orange"],
    "gemma2:2b":               PALETTE["mint"],
    "llama3.2:1b":             PALETTE["pink"],
    "phi3:mini":               PALETTE["orange"],
    "qwen2.5:7b":              PALETTE["rose"],
    "tinyllama:1.1b":          "#FCD34D",  # warm yellow rounds out the palette
    "anthropic":               PALETTE["pink"],
    "ollama":                  PALETTE["cyan"],
}


def _add_model_color_overrides(panel):
    overrides = panel.setdefault("fieldConfig", {}).setdefault("overrides", [])
    have = {
        (o.get("matcher", {}).get("id"), o.get("matcher", {}).get("options"))
        for o in overrides
    }
    for name, color in MODEL_COLOR_PINS.items():
        if ("byName", name) in have:
            continue
        overrides.append({
            "matcher": {"id": "byName", "options": name},
            "properties": [{
                "id": "color",
                "value": {"mode": "fixed", "fixedColor": color},
            }],
        })


TRANSFORMERS = {
    "stat":       transform_stat,
    "timeseries": transform_timeseries,
    "table":      transform_table,
    "bargauge":   transform_bargauge,
    "barchart":   transform_barchart,
    "piechart":   transform_piechart,
}


def apply(dashboard):
    panels = dashboard.get("panels", [])
    already_styled = any(p.get("id") == RIBBON_PANEL_ID for p in panels)

    if not already_styled:
        # 1. Push everything down to make room for the ribbon.
        for p in panels:
            p.setdefault("gridPos", {})["y"] = p["gridPos"].get("y", 0) + RIBBON_HEIGHT
        # 2. Prepend the ribbon.
        panels.insert(0, build_ribbon_panel())

    # 3. Transform every non-row panel. (Idempotent: threshold remaps are
    #    no-ops on already-soft colors, override pins skip duplicates,
    #    and stat/timeseries property sets are unconditional.)
    for panel in panels:
        ptype = panel.get("type")
        if ptype == "row" or panel.get("id") == RIBBON_PANEL_ID:
            continue
        # Let panels keep Grafana's default elevated card background so they
        # contrast with the page — matches the AI Obs product UI. The ribbon
        # is the only intentionally-transparent panel (it sits like a header
        # strip on the page background).
        panel["transparent"] = False
        fn = TRANSFORMERS.get(ptype)
        if fn:
            fn(panel)

    return dashboard


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    out = apply(data)
    serialized = json.dumps(out, indent=2)
    # Validate roundtrip.
    json.loads(serialized)
    path.write_text(serialized + "\n")
    print(f"rewrote {path}: {len(out['panels'])} panels, ribbon at id={RIBBON_PANEL_ID}")


if __name__ == "__main__":
    main()
