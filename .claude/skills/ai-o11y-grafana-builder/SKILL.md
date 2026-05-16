---
name: ai-o11y-grafana-builder
description: Produce actual Grafana dashboard JSON from a layout table (from ai-o11y-layout-composer) using design tokens, semantic panel kinds, and the rebuild-script pattern. Use after story + layout are decided. Writes dashboards/<uid>.json + a dashboards/_rebuild_<uid>.py generator. Never invents styling rules — only applies what's in _design_tokens.py + design_system.md. Always runs ai-o11y-aesthetic-pass as the last build step.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# ai-o11y-grafana-builder

The third step. Renders a layout table into actual Grafana JSON via a
Python rebuild script.

## When to trigger

When the user says ANY of:
- "Build the dashboard / generate the JSON for…"
- "Render this layout…"
- After a layout table from `ai-o11y-layout-composer` is in hand.

## What this skill does NOT do

- Does not invent palettes or sizing (must come from `_design_tokens.py`
  and the layout table).
- Does not apply the aesthetic pass directly — it CALLS it as the last
  build step.
- Does not score the result (`ai-o11y-dashboard-critic`).

## Procedure

1. **Read the layout table** produced by `ai-o11y-layout-composer`.

2. **Read the reference build** at `dashboards/_rebuild_outage_cost.py`.
   This is the canonical pattern: a Python script that constructs the
   `panels[]` array and writes JSON in-place.

3. **Read the design tokens** at `dashboards/_design_tokens.py`. Import:
   - `PALETTE`, `STATUS`, `MODEL_COLORS`
   - `SIZE`, `H`, `UNIT`, `DECIMALS`
   - `status_steps()`
   - `DS`, `STANDARD_VARS`, `ROW_TITLE`

4. **Create a new rebuild script** at
   `dashboards/_rebuild_<dashboard-uid>.py`. It MUST:
   - Have a docstring describing the story arc + archetype.
   - Define helpers `stat_panel(...)`, `text_panel(...)`, `row(...)` —
     reuse the helpers from `_rebuild_outage_cost.py` (copy or import).
   - Build `data["panels"]` by iterating the layout table.
   - Apply the kind-specific defaults from §7 of the design system:
     - `revenue.hero` → `colorMode: background`, status thresholds
       (danger→warning→healthy), `noValue: "$0"`, `instant: true` if
       the query window is `[1h]` or `[5m]`.
     - `revenue.kpi` → `colorMode: value`, status thresholds.
     - `revenue.flow.actual` → `drawStyle: bars`, `stacking: normal`,
       `step: "10m"`, per-model `byName` overrides.
     - `revenue.flow.missed` → `drawStyle: bars`, danger threshold,
       `min: 0`, transparent below 1.
     - `journey.health` / `engine.state` → state-timeline with
       value mappings (0 → red label, 1 → green label).
     - `ai.cost_per_mtoken` / `ai.model_mix` → bargauge gradient.
     - `header.ribbon` → leave it; aesthetic-pass adds it.
     - `header.row` → use `ROW_TITLE` constants if the topic matches a
       canonical row name.
   - Build `data["templating"]["list"]` using `STANDARD_VARS` plus
     archetype-specific textboxes (e.g. `avg_atc_value`,
     `baseline_atc_per_hour`, `outage_hours`, `annual_hours` for
     `outage-impact`).
   - Build `data["annotations"]["list"]` with the three auto-detection
     annotations (k3s NotReady, loadgen pod down, pod restart).

5. **LogQL/PromQL conventions**:
   - Datasources are `${datasource_loki}` and `${datasource_prom}` via
     the standard vars.
   - Loki: NO `clamp_min`, NO `$__rate_interval`. Use literal `[1m]`,
     `[5m]`, `[10m]`, `[1h]`, `[24h]`.
   - Prometheus: gating signals via
     `(sum(kube_node_status_condition{cluster="k3s",condition="Ready",status="false"} == 1) or vector(0))`
     pattern (the `or vector(0)` is required to keep the time series
     present when no errors fire).
   - Per-10-min bars: `step: "10m"` on the target, `interval: "10m"`
     on the panel, `count_over_time({...} [10m])` so windows don't
     overlap.

6. **Run the script + aesthetic pass + lint** as the build sequence:

```bash
python3 dashboards/_rebuild_<uid>.py
python3 dashboards/_apply_ai_obs_aesthetic.py dashboards/<uid>.json
python3 dashboards/dashboard_lint.py dashboards/<uid>.json
```

   If lint reports any ERROR, fix and re-run. If WARN only, note them
   and continue.

7. **Push to Grafana Cloud** via `tools/dashboards-sync.sh`:

```bash
set -a && source .env && set +a && \
  FILTER='<uid>' ./tools/dashboards-sync.sh push
```

8. **Commit + push to GitHub** (per the persistence rule — every live
   change must also land in the repo):

```bash
git add dashboards/<uid>.json dashboards/_rebuild_<uid>.py
git commit -m "feat(dashboards): build <uid> via grafana-builder skill"
TOKEN=$(gh auth token) && \
  GIT_ASKPASS=/bin/true git \
    -c "credential.helper=!f() { echo username=stephenwagner-grafana; echo password=$TOKEN; }; f" \
    push origin main
```

## Anti-patterns to refuse

- Editing the JSON directly with `Edit` calls (always regenerate via
  the Python script — JSON is the build artifact, not the source).
- Inventing hex colors that aren't in `PALETTE` / `STATUS` / `MODEL_COLORS`.
- Using `$__rate_interval` in LogQL (tenant doesn't support it).
- Using `clamp_min` in LogQL (tenant doesn't support it).
- Skipping the aesthetic pass — it's MANDATORY as the last step.
- Inventing template variables on the fly — declare them at the top of
  the rebuild script and document defaults inline.

## Hand-off

The output JSON is now ready for `ai-o11y-dashboard-critic` to score.
If the critic flags issues, return to this skill to patch the rebuild
script and re-render.
