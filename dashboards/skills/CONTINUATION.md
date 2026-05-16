# Continuation note — for the next Claude chat

This file is the "where we left off" handoff. Update it whenever a chat
ends with in-flight work; **read it at the start of every new chat
about the AI o11y demo**.

> **Last updated**: 2026-05-16 by Claude Opus 4.7
> **Last commit on `main`**: see `git log --oneline -5`

---

## 🚨 Major direction change — read this first

This is **no longer** "a set of Grafana dashboards." It is an
**AI-native observability presentation system**.

**Story is upstream of dashboards.** Tomorrow's primary task is NOT to
build dashboards — it is to write the **spoken demo script**, identify
**wow moments**, and only then decide which dashboards support each
beat.

The dashboards compile from the story, not the reverse.

**Two new artifacts** are now the top-level source of truth, ordered:

1. [`NARRATIVE.md`](NARRATIVE.md) — the *vision* (theses, framings,
   demo flow, wow moments). **Read first.**
2. [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) — the *spoken script* (6 acts,
   ~7 min). **The artifact tomorrow's work edits.**
3. [`README.md`](README.md) — pipeline + skill index (now 6 skills, the
   new `ai-o11y-demo-narrator` is upstream of all the others).
4. `../design_system.md` — visual contract (now includes §10
   conceptual primitives mirroring NARRATIVE.md).

A new 6th skill, `ai-o11y-demo-narrator`, owns the spoken script and
hands beats to `story-architect` when a dashboard rebuild is implied.

---

## The verbatim framings (do not paraphrase)

1. *"A conversation is the base unit of AI observability."*
2. *"AI changes the nature of telemetry itself."*
3. *"Observability optimized systems; now it optimizes AI."*
4. *"Using AI to optimize observability, while using observability to optimize AI."*
5. *"Shift-left turns subjective AI behavior into measurable operational systems."*

These are load-bearing. The script's opening line is the core thesis
*verbatim*. The conversation primitive is also spoken verbatim at first
use.

---

## Tomorrow's priorities (in order)

1. **Write the actual spoken demo script.** Fill in `DEMO_SCRIPT.md`
   beyond the v0 scaffold. Lock the prose for each act.
2. **Tighten the emotional arc.** Where exactly do the two wow moments
   land? (Currently: act 3 convo drill-down + act 4 missed-revenue.)
3. **Refine the conceptual explanations.** Each of the verbatim
   framings should be one short sentence in delivery. Practice each.
4. **Decide which existing dashboards serve which beat.** Cross-
   reference against `dashboards/` + `RATING.md`. Three buckets:
   - **Keep as-is** — already fits a beat well.
   - **Rebuild** — fits a beat conceptually but doesn't land. Route
     through `ai-o11y-story-architect` after the beat is locked.
   - **Retire** — doesn't fit any beat in the 7-min flow. Move out of
     the curated folder; keep accessible for ad-hoc deep dives.
5. **Evolve the skills around the finalized narrative.** Once the
   script is locked, each skill's "when to use" prose may need a
   tightening pass.
6. **Identify the demo's fallback paths.** Especially act 5 (the
   AI-investigation moment) — what if Grafana Assistant misfires
   live? Pre-record a backup.

---

## Status: design system + 6 skills shipped + outage-cost is clean against the linter

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
| **`dashboards/skills/NARRATIVE.md`** | **Project vision — read FIRST** |
| **`dashboards/skills/DEMO_SCRIPT.md`** | **The spoken script — read SECOND** |
| `dashboards/skills/README.md` | Skill index (6 skills) |
| `dashboards/design_system.md` | Visual contract spec |
| `dashboards/_design_tokens.py` | Python constants |
| `dashboards/_apply_ai_obs_aesthetic.py` | Aesthetic pass |
| `dashboards/dashboard_lint.py` | Linter |
| `dashboards/RATING.md` | Current dashboard scores |
| `dashboards/_rebuild_outage_cost.py` | Reference build |
| `.claude/skills/ai-o11y-demo-narrator/SKILL.md` | Narrator skill (NEW — upstream of everything) |
| `.claude/skills/ai-o11y-{story-architect,layout-composer,grafana-builder,aesthetic-pass,dashboard-critic}/SKILL.md` | The 5 downstream skills |

---

## Quick "I'm a new chat, what do I do?" runbook

1. **Read `NARRATIVE.md`** — understand the demo's vision.
2. **Read `DEMO_SCRIPT.md`** — understand the current spoken script.
3. **Read this file (`CONTINUATION.md`)** — understand where we left off.
4. Read `README.md` for the pipeline.
5. Read `design_system.md` §10 for the conceptual primitives.
6. Check `git log -5` and `git status` for in-flight work.
7. Skim `RATING.md` to see which dashboards need help.
8. Ask the user what they want — route to the right skill.

If the user asks "what should I work on today?" — the answer is almost
always **the spoken script** until it's locked. Dashboards are downstream.
