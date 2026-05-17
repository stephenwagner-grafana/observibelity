# ObserVIBElity AI O11y skill framework

A modular skill framework for designing the **AI o11y demo** — the
spoken narrative, the dashboards that support it, and the visual
contract that ties them together.

**Story is upstream of dashboards.** Read
[`NARRATIVE.md`](NARRATIVE.md) → [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md)
before any per-dashboard work.

The pipeline:

```
                              ┌─── ai-o11y-humanize-metric (advisor) ───┐
                              │                                          │
                              ▼                                          ▼
spoken narrative  →  story-architect  →  layout-composer  →  grafana-builder  →  aesthetic-pass  →  dashboard-critic
      ↑                                                                                  ▲                   │
demo-narrator  ←─── route narration changes back ──────────────────────────────────────  │                   │
      ↑                                                                                                       │
       └──────────────────────── route fixes back ──────────────────────────────────────────────────────────┘
```

`humanize-metric` is the only side-skill — it sits above the line and is
**consulted by** story-architect (when picking a hero), grafana-builder
(when emitting `unit` / `customUnit` / `decimals`), and dashboard-critic
(as objective ground truth for the "Human-scaled numbers" axis).

## The seven skills

Six in the linear pipeline, plus one advisor (`humanize-metric`) that
hangs off the side and gets consulted by story-architect, grafana-builder,
and dashboard-critic when a panel's value fails the glance test.

Skills live at `.claude/skills/<name>/SKILL.md`. They're invocable via
Claude Code's skill router (description-matched) or directly by name in
a chat (e.g. "use the ai-o11y-grafana-builder skill to…").

| Skill | When to use | What it produces |
|---|---|---|
| [`ai-o11y-demo-narrator`](../../.claude/skills/ai-o11y-demo-narrator/SKILL.md) | "Work on the demo script", "tighten act N", "add a wow moment", at the start of any narrative-shaping chat | Edits to `DEMO_SCRIPT.md` + `NARRATIVE.md`. Hands beats to story-architect for dashboard work. **Upstream of everything.** |
| [`ai-o11y-story-architect`](../../.claude/skills/ai-o11y-story-architect/SKILL.md) | New dashboard brief, or a beat from `DEMO_SCRIPT.md` that needs a dashboard | Story plan markdown: archetype + 5 rows with hero metrics + emotional beats |
| [`ai-o11y-layout-composer`](../../.claude/skills/ai-o11y-layout-composer/SKILL.md) | After a story plan, before JSON | Layout table: `id / kind / title / x / y / w / h` per panel |
| [`ai-o11y-grafana-builder`](../../.claude/skills/ai-o11y-grafana-builder/SKILL.md) | After a layout table, or when "regenerate this dashboard" | `dashboards/<uid>.json` + `dashboards/_rebuild_<uid>.py` |
| [`ai-o11y-aesthetic-pass`](../../.claude/skills/ai-o11y-aesthetic-pass/SKILL.md) | After every build or on-demand "make this pop" | Modified `dashboards/<uid>.json` with ribbon, soft palette, per-model pins |
| [`ai-o11y-dashboard-critic`](../../.claude/skills/ai-o11y-dashboard-critic/SKILL.md) | After every build, or "rate this dashboard" | Review report with scores + prioritized fixes routed back to the right skill |
| [`ai-o11y-humanize-metric`](../../.claude/skills/ai-o11y-humanize-metric/SKILL.md) | When a panel value fails the glance test — sci-notation, sub-1 rates, opaque per-token costs. Consulted by architect / builder / critic | Recommendation: unit, decimals, customUnit, axis_label, description, rebased PromQL, optional analogy. **Advisory — never writes JSON.** |

## Shared source-of-truth files

These are the files the skills depend on. They're versioned in the repo;
any change goes through PR review.

| File | Purpose |
|---|---|
| [`NARRATIVE.md`](NARRATIVE.md) | **Read first.** Project vision, theses, framings (conversation primitive, shift-left, recursive loop). Story is upstream of visuals. |
| [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) | The spoken 7-minute demo script (6 acts, wow moments, dashboard cues). The dashboards compile from this. |
| [`../design_system.md`](../design_system.md) | The canonical visual language: story arc, palettes, taxonomy, archetypes, lint rules, conceptual primitives (§10) |
| [`../_design_tokens.py`](../_design_tokens.py) | Executable companion: `PALETTE`, `STATUS`, `MODEL_COLORS`, `SIZE`, `H`, `UNIT`, `ROW_TITLE` |
| [`../_apply_ai_obs_aesthetic.py`](../_apply_ai_obs_aesthetic.py) | The aesthetic pass implementation |
| [`../dashboard_lint.py`](../dashboard_lint.py) | The automated linter (used by the critic skill) |
| [`../RATING.md`](../RATING.md) | Current dashboards scored 1-5 against the system |
| [`HUMANIZE_METRIC.md`](HUMANIZE_METRIC.md) | Canonical spec for the humanize-metric advisor: three modes (scale / rebase / analogy), audience denominators, analogy library, worked examples |
| [`HUMANIZE_METRIC.grafana.md`](HUMANIZE_METRIC.grafana.md) | Paste-body for the Grafana Cloud Assistant skill — self-contained re-flow of the spec. Re-paste into Assistant when the spec changes. |
| [`../humanize.py`](../humanize.py) + [`../_humanize_table.py`](../_humanize_table.py) | Executable logic + data for `ai-o11y-humanize-metric` |
| [`CONTINUATION.md`](CONTINUATION.md) | Handoff note for the next chat — open work + key context |

## The full lifecycle (what "use the skills" looks like in practice)

### Narrative work (upstream of everything else)

1. **Read `NARRATIVE.md`** — make sure you're aligned with the project
   vision and the framings (conversation primitive, shift-left,
   recursive loop, the 5 verbatim framings).
2. **Read `DEMO_SCRIPT.md`** — the spoken 7-minute script with the 6
   acts and the wow moments.
3. `ai-o11y-demo-narrator` edits the script. New beats may imply new
   dashboards, which route to step 5 below.

### Per-dashboard work (downstream of the script)

4. **Brief in plain English** to Claude (e.g. "the demo needs a
   dashboard for act 4 showing missed revenue when k3s breaks"). The
   brief should reference the demo beat it serves.
5. `ai-o11y-story-architect` returns a story plan.
6. User confirms or refines the plan.
7. `ai-o11y-layout-composer` returns a layout table.
8. `ai-o11y-grafana-builder` writes the rebuild script + JSON, runs the
   aesthetic pass + lint, and pushes to Grafana Cloud.
9. `ai-o11y-dashboard-critic` scores the result against the design
   system AND against the beat it's meant to serve.
10. Iterate: any flagged issue routes back to the originating skill.

### For an existing dashboard ("make this better"):

- Skip 5–7 if the story + layout are already sound.
- Go straight to `ai-o11y-aesthetic-pass` for color/style fixes, then
  `ai-o11y-dashboard-critic` for scoring.

### For "is this dashboard ready to demo?":

- `ai-o11y-dashboard-critic` only — but the critic should check the
  dashboard against the beat it's meant to support in `DEMO_SCRIPT.md`,
  not just against the design system.

## Hard rules the framework enforces

These are in `design_system.md` + `dashboard_lint.py`:

- **Story arc order**: business → customer → technical → AI/model → action.
- **One color track per panel**: soft palette (blue/purple/pink/orange/
  cyan/mint/rose) OR status palette (green/amber/red/muted), never both.
- **One hero per row**, sized ≥ 12w × 8h, `colorMode: background`.
- **Per-model color pins** so the same model is the same hue in every chart.
- **Human-scaled units**: `$/hr` not `$/sec`; `$/1M tokens` not `$/token`;
  `customUnit: " hours"` for unitless counts.
- **No `clamp_min` or `$__rate_interval` in LogQL** (tenant-specific).
- **Empty-state resilience**: short-window stat queries use `instant: true`
  + `noValue`.
- **Mandatory aesthetic pass** as the last build step.

## Companion docs

- [`../design_system.md`](../design_system.md) — full spec
- [`../RATING.md`](../RATING.md) — current dashboard scores
- [`CONTINUATION.md`](CONTINUATION.md) — handoff state
