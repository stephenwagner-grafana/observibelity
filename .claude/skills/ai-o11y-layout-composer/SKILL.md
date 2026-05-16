---
name: ai-o11y-layout-composer
description: Turn a story plan (from ai-o11y-story-architect) into a concrete grid layout — row order, panel sizes, x/y positions, hero placement, pacing. Use after a story plan exists but before any JSON is written. Reads the dashboard archetype + semantic panel taxonomy and emits a panel-position table. Never writes JSON; passes the table to ai-o11y-grafana-builder.
allowed-tools: Read, Grep, Glob
---

# ai-o11y-layout-composer

The second step in the lifecycle. Converts the narrative plan into a grid
layout that the grafana-builder can render mechanically.

## When to trigger

When the user says ANY of:
- "Lay out the dashboard for…"
- "How would you arrange the panels for…"
- "Place / position the panels…"
- After a story plan is in hand and before JSON is generated.

## What this skill does NOT do

- Does not pick the archetype (already done by story-architect)
- Does not write JSON or queries (that's grafana-builder)
- Does not apply palette transformations (aesthetic-pass)

## Procedure

1. **Re-read the story plan** produced by `ai-o11y-story-architect`.

2. **Look up the archetype layout** in `dashboards/design_system.md` §8.
   The archetype catalog has named templates (`outage-impact`,
   `per-user-attribution`, `app-overview`, `eval-quality`, `landing`).
   The catalog encodes typical row order + sizes.

3. **Walk the rows** in the order the story plan dictates. For each row:
   - One `header.row` (24w × 1h) at `y = next_y`. Title pattern:
     `<emoji> <topic> — <what this row tells you>`.
   - Decide the panels in the row, picking semantic kinds from §7
     (the taxonomy). Each panel has a canonical size in `SIZE` (Python
     tokens):

     | Kind                  | (w, h)  |
     |-----------------------|---------|
     | `revenue.hero`        | 12 × 8  |
     | `revenue.kpi`         | 6 × 4   |
     | `revenue.flow.actual` | 24 × 9  |
     | `revenue.flow.missed` | 24 × 8  |
     | `journey.health`      | 12 × 7  |
     | `journey.start_vs_end`| 12 × 8  |
     | `engine.state`        | 12 × 7  |
     | `engine.errors_table` | 24 × 8  |
     | `ai.cost_per_call`    | 6 × 4   |
     | `ai.cost_per_mtoken`  | 12 × 8  |
     | `ai.token_flow`       | 24 × 9  |
     | `ai.model_mix`        | 12 × 8  |
     | `ai.judge_pass_rate`  | 6 × 4   |
     | `action.runbook`      | 24 × 10 |
     | `action.alert_routes` | 24 × 6  |
     | `callout.insight`     | 8 × 8   |
     | `header.ribbon`       | 24 × 3  |
     | `header.row`          | 24 × 1  |

4. **Enforce one hero per row.** If a row has multiple candidates,
   demote all but one to KPI sizes (6 × 4 or 4 × 4 compact).

5. **Pack the row** left-to-right by `x`. A row's width must total 24
   exactly. If the row needs more space, split it into 2 rows.

6. **Bump `next_y` by the tallest panel's `h`** before starting the
   next row.

7. **Always prepend a `header.ribbon`** at `(0, 0, 24, 3)` and shift
   everything down. (The aesthetic-pass script does this automatically
   if it's missing, but the composer should plan as if it's there.)

8. **Output the layout** as a single markdown table the grafana-builder
   can consume:

```markdown
# Layout: <dashboard-uid> (<archetype>)

| id  | kind                  | title                                      | x  | y  | w  | h |
|-----|-----------------------|--------------------------------------------|----|----|----|---|
| 100 | header.ribbon         | (transparent ribbon)                       | 0  | 0  | 24 | 3 |
| 201 | header.row            | 💰 Revenue right now — what the engine is… | 0  | 3  | 24 | 1 |
| 202 | revenue.hero          | Revenue per hour — right now               | 0  | 4  | 12 | 8 |
| 203 | revenue.kpi           | Revenue — last 24 hours                    | 12 | 4  | 6  | 4 |
| …   | …                     | …                                          | …  | …  | …  | … |
```

The grafana-builder uses this table verbatim — it knows from the kind
column which Grafana panel type + thresholds + unit defaults to apply.

## Pacing rules (the small stuff that makes it feel premium)

- **Don't mix `h=7` with `h=8` in the same horizontal row.** Match
  heights left-to-right so the row reads as a single band.
- **One hero per row** (and one row per business-stage).
- **Cap row count at ~7.** > 7 rows = consider splitting.
- **Whitespace via spec**: if a row has only a hero + one supporting
  panel, place the hero at `x=8` (not `x=0`) so it sits centered with
  callouts flanking it.

## Anti-patterns to refuse

- Layouts that don't fill the row width (24-col grid must be 24, not
  20 or 28).
- Hero in a corner — heroes go left or center, never right.
- Heroes stacked vertically without a row header in between.
- The `header.ribbon` is missing or not at `y=0`.

## Hand-off

Output goes to `ai-o11y-grafana-builder`, which converts the table into
panel JSON using `_design_tokens.py` for sizes/units/colors.
