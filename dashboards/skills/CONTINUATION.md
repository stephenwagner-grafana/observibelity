# Continuation note — for the next Claude chat

This file is the "where we left off" handoff. Update it whenever a chat
ends with in-flight work; read it at the start of every new chat about
ObserVIBElity dashboards.

> **Last updated**: 2026-05-16 by Claude Opus 4.7
> **Last commit on `main`**: see `git log --oneline -5`

---

## Status: design system + 5 skills shipped + outage-cost is clean against the linter

### What's working

- **Design system spec** is comprehensive: story arc, palette + status
  tracks, per-model pins, semantic panel taxonomy (§7), archetype
  catalog (§8), lint rules spec (§9), pre-ship checklist (§4), small-
  things checklist (§5).
- **Executable tokens** at `dashboards/_design_tokens.py` — `PALETTE`,
  `STATUS`, `MODEL_COLORS`, `SIZE`, `H`, `UNIT`, `DECIMALS`,
  `status_steps()`, `STANDARD_VARS`, `ROW_TITLE`.
- **Aesthetic pass** at `dashboards/_apply_ai_obs_aesthetic.py` —
  idempotent, applies ribbon + soft palette + per-model pins.
  **Now preserves** `instant: true` on stat targets, `colorMode: background`
  on heroes, and `noValue` defaults (the previous version overwrote
  these and reintroduced flicker).
- **Linter** at `dashboards/dashboard_lint.py` — enforces lint rules
  spec from `design_system.md` §9. **`ai-obs-outage-cost` is now
  clean: 0 ERROR, 0 WARN, 0 INFO.**
- **5 skills** in `.claude/skills/ai-o11y-*/SKILL.md` — story-architect,
  layout-composer, grafana-builder, aesthetic-pass, dashboard-critic.
- **Reference build** `dashboards/_rebuild_outage_cost.py` — full
  implementation of the `outage-impact` archetype. **Projected-outage
  row was refactored**: hero is now 16w × 8h (was 8w × 8h, lint ERROR),
  thresholds are pure status palette (was mixed soft+status), and the
  four tunables moved to a 2nd sub-row at 6w × 4h each. Stacked-by-
  model bars use `palette-classic-by-name` (was `palette-classic`,
  lint ERROR).
- **Current scores** in `dashboards/RATING.md` — folder avg 4.0/5
  before this round; outage-cost is now closer to 5/5.

### What's not done yet

- The 4 lower-scored dashboards (`ai-obs-app-neoncart`, `ai-obs-cost`,
  others) have NOT been rebuilt with the new pipeline. They're still
  hand-edited JSON. The linter would flag many issues on them.
- The linter has not been wired into CI. Run it manually for now.
- The aesthetic pass has not been re-run across the whole folder
  since the new rules landed.
- No archetype rebuild scripts exist yet for `per-user-attribution`,
  `app-overview`, `eval-quality`. The grafana-builder skill will
  produce them on-demand.
- `RATING.md` hasn't been refreshed since outage-cost was patched —
  next critic run should recompute the folder average.

---

## Open design questions (sent to ChatGPT for input — see prior chat)

A. **Bar chart "pop"** — pending answer. Current plan: outline + matched
   `custom.lineWidth: 1`. ChatGPT may suggest gradient highlight or
   inner glow override.
B. **Right-rail palette enforcement** — current plan: re-run aesthetic
   pass per dashboard. Could add panel-title regex coercion.
C. **Tables** — current plan: threshold-driven cell coloring at low
   opacity. Awaiting ChatGPT's preferred recipe.
D. **Hero pop** — current plan: `colorMode: background`. ChatGPT may
   prefer subtler "value" + gradient backdrop.
E. **Story-arc linting** — DONE in `dashboard_lint.py` (rule `arc.row-order`).

ChatGPT's reply will land via a future user message. Update this file
when answers arrive.

---

## Conventions every Claude chat MUST honor

1. **Persistence rule** — every change to a live dashboard MUST also
   land in `dashboards/<uid>.json` + the matching `_rebuild_<uid>.py`
   + a git commit. Live + repo never drift.
2. **GitHub auth** — use the EBUSY workaround from
   `MEMORY.md → github_setup.md` to push.
3. **No `clamp_min` in LogQL.** No `$__rate_interval` in LogQL.
   These are tenant-specific gotchas.
4. **Dashboard sync** — push via
   `set -a && source .env && set +a && FILTER='<uid>' ./tools/dashboards-sync.sh push`.
5. **Aesthetic pass is the last build step**, ALWAYS.
6. **Critic runs after aesthetic pass**, ALWAYS, before declaring done.

---

## Important paths

| Where | What |
|---|---|
| `dashboards/design_system.md` | The full spec |
| `dashboards/_design_tokens.py` | Python constants |
| `dashboards/_apply_ai_obs_aesthetic.py` | Aesthetic pass |
| `dashboards/dashboard_lint.py` | Linter |
| `dashboards/RATING.md` | Current scores |
| `dashboards/_rebuild_outage_cost.py` | Reference build |
| `dashboards/skills/README.md` | Skill index |
| `.claude/skills/ai-o11y-*/SKILL.md` | The 5 skill specs |

---

## Quick "I'm a new chat, what do I do?" runbook

1. Read this file (`CONTINUATION.md`).
2. Read `dashboards/skills/README.md` for the pipeline.
3. Read `dashboards/design_system.md` for the rules.
4. Check `git log -5` and `git status` for in-flight work.
5. Skim `dashboards/RATING.md` to see which dashboards need help most.
6. Ask the user what they want — then route to the right skill.
