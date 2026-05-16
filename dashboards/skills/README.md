# ObserVIBElity dashboard skills

A modular skill framework for designing, building, and maintaining AI o11y
demo dashboards. Each skill is a single-responsibility step in the
dashboard lifecycle. Together they form a pipeline:

```
brief  →  story-architect  →  layout-composer  →  grafana-builder  →  aesthetic-pass  →  dashboard-critic
                                                                              ↑                  │
                                                                              └──────── route fixes back ┘
```

## The five skills

Skills live at `.claude/skills/<name>/SKILL.md`. They're invocable via
Claude Code's skill router (description-matched) or directly by name in
a chat (e.g. "use the ai-o11y-grafana-builder skill to…").

| Skill | When to use | What it produces |
|---|---|---|
| [`ai-o11y-story-architect`](../../.claude/skills/ai-o11y-story-architect/SKILL.md) | New dashboard brief, or before any other skill if no story plan exists | Story plan markdown: archetype + 5 rows with hero metrics + emotional beats |
| [`ai-o11y-layout-composer`](../../.claude/skills/ai-o11y-layout-composer/SKILL.md) | After a story plan, before JSON | Layout table: `id / kind / title / x / y / w / h` per panel |
| [`ai-o11y-grafana-builder`](../../.claude/skills/ai-o11y-grafana-builder/SKILL.md) | After a layout table, or when "regenerate this dashboard" | `dashboards/<uid>.json` + `dashboards/_rebuild_<uid>.py` |
| [`ai-o11y-aesthetic-pass`](../../.claude/skills/ai-o11y-aesthetic-pass/SKILL.md) | After every build or on-demand "make this pop" | Modified `dashboards/<uid>.json` with ribbon, soft palette, per-model pins |
| [`ai-o11y-dashboard-critic`](../../.claude/skills/ai-o11y-dashboard-critic/SKILL.md) | After every build, or "rate this dashboard" | Review report with scores + prioritized fixes routed back to the right skill |

## Shared source-of-truth files

These are the files the skills depend on. They're versioned in the repo;
any change goes through PR review.

| File | Purpose |
|---|---|
| [`../design_system.md`](../design_system.md) | The canonical visual language: story arc, palettes, taxonomy, archetypes, lint rules |
| [`../_design_tokens.py`](../_design_tokens.py) | Executable companion: `PALETTE`, `STATUS`, `MODEL_COLORS`, `SIZE`, `H`, `UNIT`, `ROW_TITLE` |
| [`../_apply_ai_obs_aesthetic.py`](../_apply_ai_obs_aesthetic.py) | The aesthetic pass implementation |
| [`../dashboard_lint.py`](../dashboard_lint.py) | The automated linter (used by the critic skill) |
| [`../RATING.md`](../RATING.md) | Current dashboards scored 1-5 against the system |
| [`CONTINUATION.md`](CONTINUATION.md) | Handoff note for the next chat — open work + key context |

## The 7-step lifecycle (what "use the skills" looks like in practice)

For a new dashboard:

1. **Brief in plain English** to Claude (e.g. "design me a dashboard
   showing customer abandonment when k3s breaks").
2. `ai-o11y-story-architect` returns a story plan.
3. User confirms or refines the plan.
4. `ai-o11y-layout-composer` returns a layout table.
5. `ai-o11y-grafana-builder` writes the rebuild script + JSON, runs the
   aesthetic pass + lint, and pushes to Grafana Cloud.
6. `ai-o11y-dashboard-critic` scores the result.
7. Iterate: any flagged issue routes back to the originating skill.

For an existing dashboard ("make this better"):

- Skip 2–4 if the story + layout are already sound.
- Go straight to `ai-o11y-aesthetic-pass` for color/style fixes, then
  `ai-o11y-dashboard-critic` for scoring.

For "is this dashboard ready to demo?":

- `ai-o11y-dashboard-critic` only.

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
