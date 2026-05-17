---
name: ai-o11y-dashboard-critic
description: Score a dashboard against the design system + run the lint rules + recommend specific fixes. Use when the user says "rate this dashboard", "review the dashboard", "what's wrong with…", "score…", or as the final step in any dashboard build/edit cycle. Returns a 1-5 score across six axes plus a prioritized list of fixes. Updates dashboards/RATING.md when scoring a folder.
allowed-tools: Read, Bash, Grep, Glob
---

# ai-o11y-dashboard-critic

The fifth and final step. Independent reviewer.

## When to trigger

When the user says ANY of:
- "Rate / score / review the dashboard…"
- "What's wrong with the dashboard at…"
- "How does the dashboard compare to the design system?"
- As the **final step** in any other skill's flow before declaring done.

## What this skill does

1. Runs `dashboards/dashboard_lint.py` to surface mechanical issues
   (ERROR / WARN / INFO).
2. Scores the dashboard 1-5 on six axes:
   - **Story arc** — does it read top-to-bottom as one narrative?
   - **Hero emphasis** — is each row's hero visually dominant?
   - **Color discipline** — one track per panel, no rainbow, per-model
     pins?
   - **Human-scaled numbers** — do units pass the glance test?
   - **Premium feel** — elevated cards, descriptions, subtle annotations?
   - **Empty-state resilience** — no flicker, no "No data" blanks?
3. Returns a **prioritized list of specific fixes**, each one
   actionable by a named other skill.
4. If the target is a folder of dashboards, updates `dashboards/RATING.md`
   with the new scores.

## What this skill does NOT do

- Does not write or modify any dashboard JSON.
- Does not auto-fix lint errors (it routes them back to the appropriate
  skill).

## Procedure

1. **Identify the target** — single dashboard JSON or the whole folder
   (`dashboards/*.json`).

2. **Run the linter** for each target:

```bash
python3 dashboards/dashboard_lint.py dashboards/<uid>.json
```

   Capture ERROR / WARN / INFO counts and the rule names.

3. **Read the JSON** and walk the six axes. Use the rubric:

| Score | Story arc                                          | Hero emphasis                         | Color discipline                              | Numbers                                              | Premium feel                                       | Empty-state                          |
|:-----:|----------------------------------------------------|---------------------------------------|-----------------------------------------------|------------------------------------------------------|----------------------------------------------------|--------------------------------------|
| 5     | 5 stages, each row owns one, action row present    | Each row has one hero ≥ 12×8, bg color | One track per panel, per-model pins present  | Every value reads at a glance, units chosen for range | Ribbon present, descriptions on every panel        | No flicker, noValue defaults present |
| 4     | All stages present but one row mixes               | Hero present but only 12×6 or 8×8     | One track per panel, missing some model pins | Some units stale (`$/token`) but mostly clean        | Ribbon present, missing some descriptions          | One short-window query w/o instant   |
| 3     | Order roughly right but action row missing         | One row has two co-equal heroes       | One panel has a Grafana-classic palette       | Several values exponential without subtitle          | Some panels off-palette, others fine               | "No data" flickers on one or two     |
| 2     | Two rows clearly out of stage                      | No clear hero                         | Multiple panels on Grafana-classic            | Half the panels fail the glance test                 | Inconsistent transparency, descriptions missing    | Multiple flickering panels           |
| 1     | No arc detectable                                  | All panels equal-sized                | Rainbow on quantitative comparisons           | Raw seconds / per-token everywhere                   | Looks like raw Grafana defaults                    | Repeated "No data" everywhere        |

   Score each axis; average across the six.

4. **Output the report** as a single markdown block:

```markdown
# Dashboard review: <uid>

**Date**: <YYYY-MM-DD>
**Linter**: <N ERROR, M WARN, K INFO>

## Scores

| Axis                       | Score | Note                                          |
|----------------------------|:-----:|-----------------------------------------------|
| Story arc                  | <n>   | <1-line note>                                 |
| Hero emphasis              | <n>   | <1-line note>                                 |
| Color discipline           | <n>   | <1-line note>                                 |
| Human-scaled numbers       | <n>   | <1-line note>                                 |
| Premium feel               | <n>   | <1-line note>                                 |
| Empty-state resilience     | <n>   | <1-line note>                                 |
| **Average**                | **<n>** | —                                           |

## Prioritized fixes

1. **<rule-name>** — <what + why>. Route to: <skill name>.
2. <…>
3. <…>

## Lint output (for the record)

<paste of dashboard_lint.py output>
```

5. **If scoring a folder**, also update `dashboards/RATING.md` with the
   new row(s) and a folder-average recompute.

6. **Route fixes** to the right skill:
   - Story-arc ERRORs / row-order issues → `ai-o11y-story-architect`
   - Hero-size / position issues → `ai-o11y-layout-composer`
   - Fails the glance test / wrong unit / wrong denominator / missing
     analogy → `ai-o11y-humanize-metric` (which then routes to
     `ai-o11y-grafana-builder` for the JSON patch)
   - Wrong query / missing var → `ai-o11y-grafana-builder`
   - Off-palette / no ribbon / classic colors → `ai-o11y-aesthetic-pass`

7. **Objective ground truth for the "Numbers" axis**: for every stat /
   hero / KPI panel, call `ai-o11y-humanize-metric` with the panel's
   metric + typical value + dashboard audience. Compare the recommended
   `unit` / `custom_unit` / `decimals` / `prom_fragment` to what's
   actually in the JSON. Each divergence drops the "Human-scaled numbers"
   score by one level. (`unit.humanize-diverges` in the linter is the
   automated form of this check.)

## Anti-patterns to refuse

- Scoring without running the linter (the rubric and the rules are
  complementary, both required).
- Suggesting fixes the linter can already catch (the linter is the
  ground truth for mechanical issues; the critic adds judgment).
- Auto-applying fixes (always route back to the appropriate skill).
- Inflating scores. A 5 is rare. The current `ai-obs-app-landing`
  reference is the 5/5 mark; everything else is judged against it.

## When to update the rubric

If a new design-system rule is added (e.g. a new color track for
"AI evals"), update both `dashboard_lint.py` and the rubric in this
file in the same commit.
