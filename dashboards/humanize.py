"""
humanize.py — convert (metric, typical value, audience) → Recommendation.

The decision logic lives here; the data lives in _humanize_table.py. The
canonical narrative lives in dashboards/skills/HUMANIZE_METRIC.md.

Public API:

    humanize(
        metric_name: str,
        typical_value: float,
        audience: str = "Mixed",
        *,
        unit_family: str | None = None,
        is_rate: bool = False,
        domain: str | None = None,
        available_series: tuple[str, ...] = (),
        prom_query: str | None = None,
        prefer_analogy: bool = False,
    ) -> Recommendation

Pure function. Deterministic. Tested by test_humanize.py.
"""

from dataclasses import dataclass, asdict, field

from _humanize_table import (
    pick_ladder_rung,
    pick_denominators,
    pick_analogy,
)


# Unit families whose Grafana unit string itself auto-formats with K/M/B
# suffixes (so we must NOT pre-divide — Grafana would double-scale).
_AUTO_SCALING_FAMILIES = {"count", "currency_usd", "percent", "tokens"}


@dataclass(frozen=True)
class Recommendation:
    mode: str                          # "scale" | "rebase" | "analogy" | "convention"
    display_value: str                 # the value as it will render
    unit: str                          # Grafana `unit` field
    custom_unit: str = ""              # Grafana `customUnit` (leading space if non-empty)
    decimals: int = 1                  # Grafana `decimals`
    axis_label: str = ""               # short title fragment
    description: str = ""              # panel description tooltip
    prom_fragment: str = ""            # PromQL the panel should use
    analogy: str | None = None         # optional tactile phrase
    notes: str = ""                    # why this mode was chosen

    def as_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _in_glance_range(v: float) -> bool:
    """Is the absolute value comfortable for a human glance?"""
    if v == 0:
        return True
    return 1.0 <= abs(v) < 1000.0


def _format(v: float, decimals: int) -> str:
    """Render a value without trailing scientific notation, capped to a sane
    decimal count."""
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.{max(decimals, 1)}f}"
    return f"{v:.{decimals}f}"


def _denominator_match(available_series, candidates):
    """Returns the first candidate metric name that's in available_series,
    or None if no match. Time-rebase denominators (empty candidates) always
    match — they project off the rate, no Prom series needed."""
    if not candidates:
        return ""        # time-based denominator — always available
    for c in candidates:
        if c in available_series:
            return c
    return None


# ---------------------------------------------------------------------------
# The decision function
# ---------------------------------------------------------------------------

def humanize(
    metric_name: str,
    typical_value: float,
    audience: str = "Mixed",
    *,
    unit_family: str | None = None,
    is_rate: bool = False,
    domain: str | None = None,
    available_series=(),
    prom_query: str | None = None,
    prefer_analogy: bool = False,
) -> Recommendation:
    """Pick a humanized representation for `typical_value` of `metric_name`.

    See dashboards/skills/HUMANIZE_METRIC.md §2 for the three modes and §5
    for the decision tree this function implements.
    """
    if is_rate:
        base_query = prom_query or f"rate({metric_name}[5m])"
    else:
        base_query = prom_query or metric_name

    # ----- Mode 3 first (when caller opts in by passing `domain`) ----------
    #
    # If the caller named a `domain`, they're asking for the executive
    # framing: scale the number with mode 1, attach a tactile analogy.
    # Mode 3 only fires for non-rate metrics (rates go through mode 2,
    # which can produce its own glanceable form). `prefer_analogy=True`
    # forces this branch even for rates.
    if domain and (not is_rate or prefer_analogy):
        analogy = pick_analogy(domain, typical_value)
        if analogy:
            rec_unit, rec_custom, rec_decimals = "short", "", 0
            rec_display = _format(typical_value, 0)
            if unit_family:
                rung = pick_ladder_rung(unit_family, typical_value)
                if rung:
                    mult, rec_unit, rec_custom, rec_decimals = rung
                    # Auto-scaling Grafana units handle K/M themselves;
                    # only divide for tier-explicit units (bytes/gbytes/etc.).
                    divisor = 1.0 if unit_family in _AUTO_SCALING_FAMILIES else mult
                    rec_display = _format(typical_value / divisor, rec_decimals)
            return Recommendation(
                mode="analogy",
                display_value=rec_display,
                unit=rec_unit,
                custom_unit=rec_custom,
                decimals=rec_decimals,
                axis_label=metric_name,
                description=f"{metric_name} — {analogy.phrase}.",
                prom_fragment=base_query,
                analogy=analogy.phrase,
                notes=(
                    f"Mode 3 (analogy): domain={domain}, "
                    f"anchored at {analogy.magnitude:g}."
                ),
            )

    # ----- Mode 0: already glanceable ---------------------------------------
    if _in_glance_range(typical_value) and unit_family and not prefer_analogy:
        rung = pick_ladder_rung(unit_family, typical_value)
        if rung:
            mult, unit, suffix, decimals = rung
            if mult == _base_multiplier(unit_family):
                return Recommendation(
                    mode="convention",
                    display_value=_format(typical_value, decimals),
                    unit=unit,
                    custom_unit=suffix,
                    decimals=decimals,
                    axis_label=metric_name,
                    description=f"{metric_name} at typical scale — already glanceable.",
                    prom_fragment=base_query,
                    notes="Value already lands in 1–999; no rebase needed.",
                )

    # ----- Mode 1: SI / unit-family scaling --------------------------------
    if unit_family and not prefer_analogy:
        rung = pick_ladder_rung(unit_family, typical_value)
        if rung:
            mult, unit, suffix, decimals = rung
            # Auto-scaling Grafana units (short / currencyUSD / percent)
            # format their own K/M/B for any value ≥ 1; pre-dividing would
            # double-scale. Tier-explicit units (gbytes/ms/...) need
            # pre-division by the rung's multiplier.
            auto = unit_family in _AUTO_SCALING_FAMILIES
            if auto:
                # Grafana auto-format only saves us when |value| ≥ 1.
                # Sub-1 values must fall through to rebase / analogy.
                if abs(typical_value) >= 1.0:
                    return Recommendation(
                        mode="scale",
                        display_value=_format(typical_value, decimals),
                        unit=unit,
                        custom_unit=suffix,
                        decimals=decimals,
                        axis_label=f"{metric_name} ({unit}{suffix})".strip(),
                        description=f"{metric_name} — Grafana auto-formats K/M/B.",
                        prom_fragment=base_query,
                        notes=f"Mode 1 (auto-scale): {unit_family}, Grafana renders K/M.",
                    )
            else:
                scaled = typical_value / mult
                if _in_glance_range(scaled):
                    prom_fragment = base_query if mult == 1 else f"({base_query}) / {mult:g}"
                    return Recommendation(
                        mode="scale",
                        display_value=_format(scaled, decimals),
                        unit=unit,
                        custom_unit=suffix,
                        decimals=decimals,
                        axis_label=f"{metric_name} ({unit}{suffix})".strip(),
                        description=f"{metric_name} — scaled to glanceable units.",
                        prom_fragment=prom_fragment,
                        notes=f"Mode 1 (SI scale): {unit_family}, factor {mult:g}.",
                    )

    # ----- Mode 2: denominator rebasing ------------------------------------
    #
    # Walk the audience's preferred denominator list in order. Population
    # denominators (customers, requests, …) come first by construction;
    # time denominators (month, day, hour, …) are the fallback within the
    # same list. Each entry is tried; first match wins.
    if is_rate:
        for denom in pick_denominators(audience):
            if denom.metric_candidates:
                # 2a — population/volume denominator. Needs a real series.
                match = _denominator_match(available_series, denom.metric_candidates)
                if not match:
                    continue
                return Recommendation(
                    mode="rebase",
                    display_value="—",      # downstream computes from live data
                    unit="none",
                    custom_unit=f" per {denom.short_label}",
                    decimals=0,
                    axis_label=f"{metric_name} per {denom.short_label}",
                    description=(
                        f"{denom.description_phrase}, this many "
                        f"{_short_metric_label(metric_name)}."
                    ),
                    prom_fragment=(
                        f"rate({metric_name}[5m]) / rate({match}[5m]) "
                        f"* {denom.target_basis}"
                    ),
                    notes=(
                        f"Mode 2 (population-rebase): audience={audience}, "
                        f"denominator={denom.name}, basis={denom.target_basis}, "
                        f"series={match}."
                    ),
                )
            else:
                # 2b — time denominator. Only apply if it lands in 1–999.
                projected = typical_value * denom.target_basis
                if not _in_glance_range(projected):
                    continue
                unit = "currencyUSD" if unit_family == "currency_usd" else "short"
                return Recommendation(
                    mode="rebase",
                    display_value=_format(projected, 2),
                    unit=unit,
                    custom_unit=f" /{denom.name}",
                    decimals=2,
                    axis_label=f"{metric_name} /{denom.name}",
                    description=(
                        f"At the current rate of {_short_metric_label(metric_name)}, "
                        f"projected per {denom.name}."
                    ),
                    prom_fragment=f"rate({metric_name}[5m]) * {denom.target_basis}",
                    notes=(
                        f"Mode 2 (time-rebase): audience={audience}, "
                        f"factor={denom.target_basis}."
                    ),
                )

    # ----- Mode 3: magnitude-fit analogy -----------------------------------
    if domain:
        analogy = pick_analogy(domain, typical_value)
        if analogy:
            # Also scale to nearest SI for the displayed number.
            rec_unit, rec_custom, rec_decimals = "short", "", 0
            rec_display = _format(typical_value, 0)
            if unit_family:
                rung = pick_ladder_rung(unit_family, typical_value)
                if rung:
                    mult, rec_unit, rec_custom, rec_decimals = rung
                    rec_display = _format(typical_value / mult, rec_decimals)
            return Recommendation(
                mode="analogy",
                display_value=rec_display,
                unit=rec_unit,
                custom_unit=rec_custom,
                decimals=rec_decimals,
                axis_label=metric_name,
                description=f"{metric_name} — {analogy.phrase}.",
                prom_fragment=base_query,
                analogy=analogy.phrase,
                notes=f"Mode 3 (analogy): domain={domain}, anchored at {analogy.magnitude:g}.",
            )

    # ----- Fallback: convention ----------------------------------------------
    return Recommendation(
        mode="convention",
        display_value=_format(typical_value, 2),
        unit="short",
        custom_unit="",
        decimals=2,
        axis_label=metric_name,
        description=f"{metric_name} — no humanization rule matched; review the unit.",
        prom_fragment=base_query,
        notes="No mode applied. Consider supplying domain= or unit_family=.",
    )


def _short_metric_label(metric_name: str) -> str:
    """Best-effort: strip Prom suffixes for use in a description sentence."""
    label = metric_name.replace("_total", "").replace("_count", "")
    label = label.replace("_", " ")
    return label


def _base_multiplier(family: str) -> float:
    """The lowest rung's multiplier for a unit family — 'base' means 'no scaling'."""
    rungs = {
        "time": 1.0,        # second
        "bytes": 1.0,       # byte
        "currency_usd": 1.0,
        "power": 1.0,       # watt
        "count": 1.0,
        "tokens": 1.0,
        "ratio": 1.0,
    }
    return rungs.get(family, 1.0)


# ---------------------------------------------------------------------------
# CLI for ad-hoc lookups (optional convenience)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, json, sys
    p = argparse.ArgumentParser()
    p.add_argument("metric")
    p.add_argument("value", type=float)
    p.add_argument("--audience", default="Mixed")
    p.add_argument("--unit-family", default=None)
    p.add_argument("--rate", action="store_true")
    p.add_argument("--domain", default=None)
    p.add_argument("--series", nargs="*", default=())
    p.add_argument("--prefer-analogy", action="store_true")
    args = p.parse_args()
    rec = humanize(
        args.metric,
        args.value,
        args.audience,
        unit_family=args.unit_family,
        is_rate=args.rate,
        domain=args.domain,
        available_series=tuple(args.series),
        prefer_analogy=args.prefer_analogy,
    )
    json.dump(rec.as_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
