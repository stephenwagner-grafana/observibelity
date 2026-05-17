#!/usr/bin/env python3
"""
ObserVIBElity dashboard linter.

Enforces the rules spec in `dashboards/design_system.md` §9. Reads a
dashboard JSON file, walks the panels + queries, emits issues with
ERROR / WARN / INFO severity. Exit code 0 = no ERRORs; non-zero = at
least one ERROR.

Usage:
  python3 dashboards/dashboard_lint.py dashboards/<uid>.json
  python3 dashboards/dashboard_lint.py dashboards/*.json
"""
from __future__ import annotations
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# ----- design-system imports (kept lightweight so this file is portable) ------

PALETTE_HEXES = {"#8AB8FF", "#A78BFA", "#F472B6", "#FB923C", "#67E8F9", "#86EFAC", "#FCA5A5"}
STATUS_HEXES = {"#10B981", "#F59E0B", "#EF4444", "#9CA3AF"}
CANONICAL_ROW_EMOJIS = {"💰", "👥", "📈", "🤖", "💡", "🛑", "📉", "📊", "🎯"}
KNOWN_MODELS = {
    "claude-opus-4-7", "claude-opus-4-5", "claude-opus-4-5-20251015",
    "claude-sonnet-4-6", "claude-haiku-4-5", "claude-haiku-4-5-20251001",
    "gemma2:2b", "llama3.2:1b", "llama3.2:latest", "llama3.1:8b",
    "phi3:mini", "qwen2.5:7b", "qwen3:30b-a3b-instruct-2507-q4_K_M",
    "tinyllama:1.1b", "anthropic", "ollama",
}
# Canonical story-arc stages by row-title emoji.
ROW_STAGE_BY_EMOJI = {
    "💰": "business", "📉": "business", "🛑": "business",
    "👥": "customer",
    "📈": "technical", "📊": "technical",
    "🤖": "ai", "🎯": "ai",
    "💡": "action",
}
CANONICAL_STAGE_ORDER = ["business", "customer", "technical", "ai", "action"]

# ----- issue model -----------------------------------------------------------

@dataclass
class Issue:
    severity: str  # ERROR | WARN | INFO
    rule: str
    panel_id: int | None
    message: str

    def fmt(self) -> str:
        loc = f"panel {self.panel_id}" if self.panel_id is not None else "dashboard"
        return f"  {self.severity:5} {self.rule:34} [{loc}] {self.message}"


# ----- rule helpers ----------------------------------------------------------

def _walk_targets(panel: dict) -> Iterable[dict]:
    for t in panel.get("targets") or []:
        yield t


def _expr(target: dict) -> str:
    return target.get("expr") or target.get("query") or target.get("rawSql") or ""


def _datasource_type(target: dict, panel: dict) -> str:
    ds = target.get("datasource") or panel.get("datasource") or {}
    return ds.get("type", "")


def _is_short_window_loki(expr: str) -> bool:
    return bool(re.search(r"\[(1m|2m|5m|10m|15m|30m|1h)\]", expr))


def _color_steps(panel: dict) -> list:
    return (
        (panel.get("fieldConfig") or {}).get("defaults", {})
        .get("thresholds", {})
        .get("steps", [])
    )


def _override_byname(panel: dict, name: str) -> bool:
    for o in (panel.get("fieldConfig") or {}).get("overrides", []) or []:
        m = o.get("matcher", {})
        if m.get("id") == "byName" and m.get("options") == name:
            return True
    return False


# ----- rules ----------------------------------------------------------------

def check_arc_row_order(dash, issues):
    """ERROR arc.row-order — row title emojis must follow the canonical 5-stage order."""
    stages_seen = []
    panels = dash.get("panels") or []
    for p in panels:
        if p.get("type") != "row":
            continue
        title = p.get("title") or ""
        # Find an emoji we recognize
        stage = None
        for emoji, st in ROW_STAGE_BY_EMOJI.items():
            if emoji in title:
                stage = st
                break
        if stage:
            stages_seen.append((p.get("id"), stage, title))

    # Are the stages in canonical order?
    last_idx = -1
    seen_action = False
    for pid, stage, title in stages_seen:
        idx = CANONICAL_STAGE_ORDER.index(stage)
        if idx < last_idx:
            issues.append(Issue(
                "ERROR", "arc.row-order", pid,
                f"row '{title}' (stage={stage}) appears AFTER a {CANONICAL_STAGE_ORDER[last_idx]} row",
            ))
        if stage == "action":
            seen_action = True
        last_idx = max(last_idx, idx)

    if stages_seen and not seen_action:
        issues.append(Issue(
            "WARN", "arc.missing-action", None,
            "dashboard has stage rows but no 💡 action row at the end",
        ))

    if len(stages_seen) > 7:
        issues.append(Issue(
            "INFO", "arc.too-long", None,
            f"dashboard has {len(stages_seen)} stage rows — consider splitting",
        ))


def check_hero_emphasis(dash, issues):
    """Hero rules from §9.

    The first non-row stat panel below each header row should be the hero.
    """
    panels = sorted(dash.get("panels") or [], key=lambda p: (p.get("gridPos", {}).get("y", 0), p.get("gridPos", {}).get("x", 0)))
    in_row = False
    first_after_row: dict | None = None
    for p in panels:
        if p.get("type") == "row":
            in_row = True
            first_after_row = None
            continue
        if in_row and first_after_row is None and p.get("type") == "stat":
            first_after_row = p
            in_row = False
            # Run hero checks on first_after_row
            title = (p.get("title") or "").lower()
            if "tunable" in title or "ref" in title:
                continue
            gp = p.get("gridPos") or {}
            if gp.get("w", 0) < 12 or gp.get("h", 0) < 8:
                issues.append(Issue(
                    "ERROR", "hero.too-small", p.get("id"),
                    f"hero stat is {gp.get('w', 0)}w × {gp.get('h', 0)}h; need ≥ 12w × 8h",
                ))
            opts = p.get("options") or {}
            if opts.get("colorMode") != "background":
                issues.append(Issue(
                    "WARN", "hero.no-color-mode", p.get("id"),
                    f"hero stat colorMode='{opts.get('colorMode', '?')}'; should be 'background'",
                ))
            if not p.get("description"):
                issues.append(Issue(
                    "WARN", "hero.no-description", p.get("id"),
                    "hero stat has no description (the (i) tooltip)",
                ))


def check_color_rules(dash, issues):
    """Color rules from §9."""
    quantitative_types = {"timeseries", "bargauge", "barchart", "table"}
    for p in dash.get("panels") or []:
        ptype = p.get("type")
        defaults = (p.get("fieldConfig") or {}).get("defaults", {})
        color_cfg = defaults.get("color") or {}
        # rainbow-on-quantitative
        if (
            color_cfg.get("mode") == "palette-classic"
            and ptype in quantitative_types
        ):
            issues.append(Issue(
                "ERROR", "color.rainbow-on-quantitative", p.get("id"),
                f"{ptype} uses 'palette-classic' (rainbow); switch to thresholds or palette-classic-by-name",
            ))
        # mixed-tracks
        step_colors = [s.get("color") for s in _color_steps(p) if isinstance(s.get("color"), str)]
        soft_hits = any(c in PALETTE_HEXES for c in step_colors)
        status_hits = any(c in STATUS_HEXES for c in step_colors)
        if soft_hits and status_hits:
            issues.append(Issue(
                "WARN", "color.mixed-tracks", p.get("id"),
                "thresholds mix soft palette + status palette hexes; pick one track per panel",
            ))
        # model-pin-missing
        for t in _walk_targets(p):
            lf = t.get("legendFormat") or ""
            if "{{" not in lf and lf in KNOWN_MODELS:
                if not _override_byname(p, lf):
                    issues.append(Issue(
                        "INFO", "color.model-pin-missing", p.get("id"),
                        f"series '{lf}' is a known model but has no byName color override",
                    ))


def check_unit_rules(dash, issues):
    """Unit rules from §9."""
    for p in dash.get("panels") or []:
        if p.get("type") != "stat":
            continue
        defaults = (p.get("fieldConfig") or {}).get("defaults", {})
        unit = defaults.get("unit") or ""
        custom_unit = defaults.get("custom", {}).get("customUnit", "") if isinstance(defaults.get("custom"), dict) else ""
        title = p.get("title") or ""
        decimals = defaults.get("decimals")
        # unit.per-token
        if "/token" in unit and "/1M" not in unit:
            issues.append(Issue(
                "WARN", "unit.per-token", p.get("id"),
                f"stat unit '{unit}' is per-token; prefer '$/1M tokens' (custom suffix)",
            ))
        # unit.degenerate-hours
        if unit == "h":
            issues.append(Issue(
                "WARN", "unit.degenerate-hours", p.get("id"),
                "unit 'h' shows '3.0 hour'; use customUnit ' hours' and unit 'none' instead",
            ))
        # unit.exponential — only a heuristic: short unit + currency-shaped title
        if unit in {"short", ""} and re.search(r"\$|cost|revenue", title, re.I):
            issues.append(Issue(
                "WARN", "unit.exponential", p.get("id"),
                f"stat looks like money ('{title}') but unit is '{unit or 'unset'}'; use currencyUSD",
            ))
        # unit.humanize-suggested — narrow heuristic. Only fires when
        # there's a real signal that the panel may render unreadably:
        # high decimals (sci-notation territory), or rate-shaped title
        # with an unscaled `short`/empty unit. Already-humanized panels
        # (currencyUSD, percent, customUnit set) are left alone.
        decimals_high = isinstance(decimals, int) and decimals >= 4
        title_l = title.lower()
        rate_shaped = bool(re.search(r"per (sec|second)\b|/sec\b|/s\b", title_l))
        raw_unit = unit in {"short", "", "none"} and not custom_unit
        if decimals_high or (rate_shaped and raw_unit):
            issues.append(Issue(
                "INFO", "unit.humanize-suggested", p.get("id"),
                (
                    f"stat '{title}' may fail the glance test "
                    f"(decimals={decimals}, unit='{unit}', customUnit='{custom_unit}'). "
                    f"Consider ai-o11y-humanize-metric for a rebased denominator."
                ),
            ))


def check_empty_state(dash, issues):
    """Empty-state rules from §9."""
    for p in dash.get("panels") or []:
        if p.get("type") != "stat":
            continue
        defaults = (p.get("fieldConfig") or {}).get("defaults", {})
        if "noValue" not in defaults:
            issues.append(Issue(
                "INFO", "query.no-novalue", p.get("id"),
                "stat panel has no noValue fallback; set to '$0' / '—' for empty-result resilience",
            ))
        # flicker-risk: Loki + short window + range=true
        for t in _walk_targets(p):
            if _datasource_type(t, p) != "loki":
                continue
            expr = _expr(t)
            if _is_short_window_loki(expr) and t.get("range") and not t.get("instant"):
                issues.append(Issue(
                    "WARN", "query.flicker-risk", p.get("id"),
                    "Loki short-window stat with range=true; set instant=true to avoid 'No data' flicker",
                ))


def check_loki_tenant_rules(dash, issues):
    """Tenant-specific LogQL rules (clamp_min + $__rate_interval)."""
    for p in dash.get("panels") or []:
        for t in _walk_targets(p):
            if _datasource_type(t, p) != "loki":
                continue
            expr = _expr(t)
            if "clamp_min(" in expr:
                issues.append(Issue(
                    "ERROR", "loki.clamp-min", p.get("id"),
                    "LogQL clamp_min(...) not supported on this Loki tenant",
                ))
            if "$__rate_interval" in expr:
                issues.append(Issue(
                    "ERROR", "loki.rate-interval-var", p.get("id"),
                    "$__rate_interval not supported in LogQL on this tenant; use literal [1m] / [5m]",
                ))


def check_aesthetic(dash, issues):
    """Aesthetic-pass rules from §9."""
    panels = sorted(dash.get("panels") or [], key=lambda p: (p.get("gridPos", {}).get("y", 0), p.get("gridPos", {}).get("x", 0)))
    if not panels:
        return
    first = panels[0]
    # Either an explicit id=100 ribbon, or any transparent panel at y=0 with h≤3.
    is_ribbon = (
        first.get("id") == 100
        or (
            (first.get("gridPos") or {}).get("y") == 0
            and (first.get("gridPos") or {}).get("h", 999) <= 3
            and first.get("transparent")
        )
    )
    if not is_ribbon:
        issues.append(Issue(
            "ERROR", "aesthetic.no-ribbon", first.get("id"),
            "first panel is not the ribbon (id=100, transparent, y=0, h≤3); run _apply_ai_obs_aesthetic.py",
        ))
    for p in panels:
        if p.get("type") in {"row", "text"}:
            continue
        if p.get("id") == 100:
            continue
        if p.get("transparent"):
            issues.append(Issue(
                "WARN", "aesthetic.transparent-panel", p.get("id"),
                f"non-ribbon non-text panel (type={p.get('type')}) has transparent=true; loses elevated-card feel",
            ))


# ----- driver ---------------------------------------------------------------

RULES = [
    check_arc_row_order,
    check_hero_emphasis,
    check_color_rules,
    check_unit_rules,
    check_empty_state,
    check_loki_tenant_rules,
    check_aesthetic,
]


def lint_file(path: Path) -> tuple[int, int, int]:
    """Return (errors, warns, infos)."""
    print(f"\n=== {path} ===")
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print(f"  ERROR parse: {e}")
        return 1, 0, 0
    issues: list[Issue] = []
    for rule in RULES:
        rule(data, issues)
    errors = sum(1 for i in issues if i.severity == "ERROR")
    warns = sum(1 for i in issues if i.severity == "WARN")
    infos = sum(1 for i in issues if i.severity == "INFO")
    # Print in severity order
    for sev in ("ERROR", "WARN", "INFO"):
        for i in issues:
            if i.severity == sev:
                print(i.fmt())
    summary = f"  → {errors} ERROR, {warns} WARN, {infos} INFO"
    print(summary)
    return errors, warns, infos


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    total_errors = 0
    total_warns = 0
    total_infos = 0
    for arg in sys.argv[1:]:
        for path in sorted(Path().glob(arg)) if "*" in arg else [Path(arg)]:
            e, w, i = lint_file(path)
            total_errors += e
            total_warns += w
            total_infos += i
    print(f"\nTotal: {total_errors} ERROR, {total_warns} WARN, {total_infos} INFO")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
