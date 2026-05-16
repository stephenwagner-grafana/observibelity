---
name: ai-o11y-aesthetic-pass
description: Apply the premium AI O11y visual language to an existing dashboard JSON — palette discipline, ribbon, soft thresholds, per-model color pins, elevated cards. Use when the user says "make this dashboard pop", "apply the aesthetic", "fix the colors", or as the mandatory last step in any dashboard build/edit cycle. Idempotent. Runs dashboards/_apply_ai_obs_aesthetic.py.
allowed-tools: Read, Bash, Edit
---

# ai-o11y-aesthetic-pass

The fourth step. Applies the visual contract to an existing dashboard.
This is the layer that turns "functional Grafana" into "executive-demo
polished Grafana".

## When to trigger

When the user says ANY of:
- "Make this dashboard pop"
- "Apply the aesthetic / style / look-and-feel"
- "Fix the colors on…"
- "Soften the palette on…"
- "Add the ribbon to…"
- OR as the **mandatory last step** in any other skill's flow before
  pushing to Grafana Cloud.

## What this skill does

1. Adds a `header.ribbon` at `(0, 0, 24, 3)` if missing (id=100,
   `transparent: true`, blue→purple→pink→orange gradient bar series
   driven by `gen_ai_client_token_usage_total` rate).
2. Softens any legacy threshold colors (e.g. raw "green"/"yellow"/"red"
   names) to the soft palette via `COLOR_MAP`.
3. Pins per-model series to their canonical hue using `MODEL_COLOR_PINS`
   field overrides (claude-opus → purple, sonnet → blue, haiku → cyan,
   etc.).
4. Stat panels: forces `colorMode: value` + `graphMode: area` (sparkline
   backdrop). Re-enables range queries on stats so the sparkline renders.
5. Timeseries: smooths line interpolation, sets gradient-opacity fills,
   bumps stacked fill opacity for the soft-glow effect.
6. Tables / bargauges: softens thresholds + forces gradient display
   mode.
7. Barcharts: switches the threshold table to a percentage gradient so
   taller bars get visibly hotter colors.
8. Piecharts: forces donut style.
9. Sets `transparent: false` on every non-ribbon non-callout panel so
   the elevated-card chrome shows.

## What this skill does NOT do

- Does not change panel positions, sizes, or row order (that's the
  composer's job).
- Does not change queries (that's the builder's job).
- Does not score or refuse panels (that's the critic's job).
- Does not edit the rebuild script — it modifies the JSON in place.

## Procedure

1. **Identify the target file** — usually `dashboards/<uid>.json`.

2. **Run the aesthetic helper** (idempotent — safe to run multiple times):

```bash
python3 dashboards/_apply_ai_obs_aesthetic.py dashboards/<uid>.json
```

3. **Verify the diff** is sensible:

```bash
git diff dashboards/<uid>.json
```

   Expect to see:
   - A new ribbon panel (id=100) at y=0
   - All other panels' `gridPos.y` bumped by 3
   - Threshold step colors swapped to palette hex values
   - `byName` overrides appearing for any model series in the queries
   - `colorMode: value` + `graphMode: area` on stat panels
   - `lineInterpolation: smooth` on timeseries

4. **Push to Grafana Cloud** so the live dashboard picks up the change:

```bash
set -a && source .env && set +a && \
  FILTER='<uid>' ./tools/dashboards-sync.sh push
```

5. **Commit + push to repo** (the persistence rule — live + repo must
   stay in sync):

```bash
git add dashboards/<uid>.json
git commit -m "style(dashboards): aesthetic pass on <uid>"
TOKEN=$(gh auth token) && \
  GIT_ASKPASS=/bin/true git \
    -c "credential.helper=!f() { echo username=stephenwagner-grafana; echo password=$TOKEN; }; f" \
    push origin main
```

## Idempotence guarantees

The script checks for an existing ribbon at id=100 before adding one.
Threshold color remaps are no-ops on hex values. `byName` overrides
skip if a matching matcher already exists. So running this multiple
times is safe and predictable.

## When to extend the helper (`_apply_ai_obs_aesthetic.py`)

- New model appears in the demo → add it to `MODEL_COLOR_PINS`
- New legacy color name appears → add to `COLOR_MAP`
- New panel type adopted → add a `transform_<type>(panel)` function
  and register in `TRANSFORMERS`

Always update `dashboards/_design_tokens.py` (`MODEL_COLORS`) and
`dashboards/design_system.md` (per-model pin table in §2.2) in the
same commit.

## Anti-patterns to refuse

- Editing the dashboard JSON to apply colors panel-by-panel — always
  use the helper.
- Skipping the helper because "the dashboard already looks fine" — it's
  idempotent, just run it.
- Adding hex values directly into queries or field configs without
  threading them through `PALETTE` / `STATUS` / `MODEL_COLORS`.

## Hand-off

After this pass, run `ai-o11y-dashboard-critic` to score the result.
