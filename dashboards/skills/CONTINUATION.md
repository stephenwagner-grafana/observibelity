# Continuation note — for the next Claude chat

This file is the "where we left off" handoff. Update it whenever a chat
ends with in-flight work; **read it at the start of every new chat
about the AI o11y demo**.

> **Last updated**: 2026-05-16 by Claude Opus 4.7 (narrator pass — script v1 locked, 3 wow moments, 6th framing added)
> **Last commit on `main`**: see `git log --oneline -5`

---

## What changed in the latest narrator pass (2026-05-16)

1. **`DEMO_SCRIPT.md` is now v1** — locked prose for all 6 acts, not a
   scaffold. Time budget is 7:15, well within ±45s.
2. **Three wow moments** (was two): added the **recursive
   meta-conversation** in Act 5 — the conversation with Grafana
   Assistant appears, in real time, on the same `ai-obs-app-neoncart`
   bar chart that showed customer conversations in Act 3.
3. **97.7% / $2.67 cold open** — new Act 1 hook (7.6M tokens, $114
   Claude-equivalent vs. $2.67 local) that pays back as a callback in
   Act 4 (~18,000× ratio vs. a 45-second outage).
4. **6th verbatim framing** added: *"Observability is the control plane
   for AI systems."* — replaces the earlier "operating system"
   phrasing in the Act 6 close.
5. **Dashboard cues consolidated** to **3 dashboards / 2 switches**
   (was implied 5–6 switches). The trick: Acts 1, 2, 3, and 6 all live
   on `ai-obs-app-neoncart` and use *scroll* not *switch*. Switches
   happen only for Act 4 (→ outage-cost) and Act 5 (→ wags-ai).
6. **Trim/add levers documented** for ±15s pacing adjustments without
   losing wow moments.

---

## Things the next chat needs to settle (in priority order)

These are the user-facing open questions from the new `DEMO_SCRIPT.md`.
Highest-impact first:

1. 🔴 **Grafana Assistant readiness for Act 5.** `gcx_setup.md` notes
   we're past the auth wall but hit `usage_limit_reached`. Demo Day
   blocker. Either resolve provisioning or pre-record the fallback
   clip *now*.
2. 🔴 **Confirm Assistant emits `gen_ai_*` telemetry** that lands in
   `ai-obs-app-neoncart`'s bar chart. If it doesn't, Wow #3 doesn't
   work. May require routing the Assistant traffic through Sigil or
   tagging it on the gateway side.
3. 🟡 **Add a cost-savings KPI to `ai-obs-outage-cost`** for the Act 4
   callback (the $2.67 vs $114-equivalent comparison). Visible payoff
   > verbal-only payoff. Route to `ai-o11y-story-architect`.
4. 🟡 **Confirm the drill-down drawer works** on
   `ai-obs-app-neoncart`'s `📦 Specialists` bar chart. The visual
   payoff of Wow #1 depends on it. If it's hand-wave-only, route to
   `ai-o11y-story-architect` for a layout fix.
5. 🟢 **Visual cue for shift-left.** Implicit via soft palette
   gradient. Open question: should it be explicit (recurring legend)?
   *Current recommendation*: leave implicit.
6. 🟢 **Decide whether Act 2 should switch to Explore.** *Current
   recommendation*: stay on neoncart top rows (saves a switch).

---

## Resolved this pass

- ~~"What's the precise opening line of Act 1?"~~ → 97.7% / $2.67 hook
  (then thesis verbatim).
- ~~"What's the fallback if Grafana Assistant misfires in act 5?"~~ →
  Pre-recorded 30s clip kept in a tab, with the meta-conversation as
  the load-bearing beat (not the Assistant query). Production of clip
  is now a TODO.
- ~~"Should there be a 30-second intermission between Acts 3 and 4?"~~
  → No. The Act 3 → Act 4 transition ("if a conversation is the unit,
  what's the unit cost?") is the natural pivot — handled in prose.

---

## Skills / lint evolutions to consider (proposed, NOT applied)

These came up while solidifying the script. Don't silently apply —
discuss with the user first:

1. **New lint rule (proposal)**: `arc.97-callback` — `outage-impact`
   archetype dashboards SHOULD surface a cost-savings KPI visible in
   ≤ 1 panel. *Severity: INFO* (nudge, not error). Rationale: the Act
   4 callback is now a load-bearing narrative element; dashboards
   playing the Act 4 role should give it visual support.
2. **Narrator skill hard-rule update**: add to `ai-o11y-demo-narrator/
   SKILL.md` Hard Rules section — *"The 97.7% cold open + Act 4
   callback is load-bearing; do not cut either without restructuring
   Act 1 and Act 4 together."*
3. **Story-architect hint**: when serving an Act 4 beat, the architect
   should default to including a "cost ratio" panel comparing local
   marginal cost vs. equivalent-managed-API cost.

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

(*Most of "yesterday's priorities" were closed in the latest narrator
pass — see "What changed" above. These are the next steps.*)

1. **Resolve the Grafana Assistant readiness for Act 5.** This is the
   #1 demo-day blocker. Unblock provisioning OR record the fallback
   clip. **Don't ship the demo without one or the other working.**
2. **Confirm Assistant telemetry lands on neoncart's bar chart.** Wow
   #3 depends on the meta-conversation being visible. Test before
   recording the fallback.
3. **Add the cost-savings KPI to `ai-obs-outage-cost`** for the Act 4
   callback. Route to `ai-o11y-story-architect` with the brief: "Act
   4 needs a KPI comparing local-marginal cost vs. equivalent-Claude
   cost (~$2.67 vs ~$114 today, the 97.7% ratio)."
4. **Confirm the drill-down works** on `ai-obs-app-neoncart`'s
   `📦 Specialists` bar. If it's vapor, fix it — Wow #1 depends on it.
5. **Rebuild candidates from `RATING.md`** — defer until #1–#4 are
   green. The remaining low-scored dashboards are *not* on the demo
   path (the demo only uses 3 dashboards now), so they're lower
   priority than they were before this narrator pass.
6. **Record a full dry run** of the 7-minute demo with a timer.
   Validate the time budget. Confirm transitions feel cinematic, not
   choppy.

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
