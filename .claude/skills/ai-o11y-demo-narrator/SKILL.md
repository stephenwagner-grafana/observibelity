---
name: ai-o11y-demo-narrator
description: Author and refine the SPOKEN demo script for the AI o11y demo. Use when the user says "work on the demo script", "tighten act N", "rewrite the narration", "add a wow moment", or anything about the demo's narrative arc. Reads dashboards/skills/NARRATIVE.md + DEMO_SCRIPT.md as the source of truth. Compiles story-beats into dashboard requirements, then hands off to ai-o11y-story-architect for per-dashboard plans. Never writes JSON; story is upstream of dashboards.
allowed-tools: Read, Write, Edit, Grep, Glob
---

# ai-o11y-demo-narrator

The **zero-th** step in the lifecycle — upstream of even `story-architect`.
Owns the spoken demo script. The dashboards compile from this script.

## When to trigger

When the user says ANY of:
- "Work on the demo script"
- "Tighten act N / the opening / the close"
- "Rewrite the narration for…"
- "Add / move / refine a wow moment"
- "What does this dashboard say in the demo?"
- "Map the demo beats to dashboards"

OR at the start of any new chat about the demo, **read** the script as
the first step before doing any dashboard work.

## What this skill does NOT do

- Does not write or modify dashboard JSON.
- Does not pick panel positions (`ai-o11y-layout-composer`).
- Does not score (`ai-o11y-dashboard-critic`).
- Does not write the design-system spec.

## Source of truth

- [`dashboards/skills/NARRATIVE.md`](../../../dashboards/skills/NARRATIVE.md) —
  project vision, theses, framings. **Read first.**
- [`dashboards/skills/DEMO_SCRIPT.md`](../../../dashboards/skills/DEMO_SCRIPT.md) —
  the spoken script itself. **The artifact you edit.**

## Procedure

1. **Read NARRATIVE.md** — make sure your edits stay consistent with:
   - the core thesis (the recursive sentence)
   - the conversation-as-primitive framing
   - the shift-left axis
   - the strongest conceptual framings (quote verbatim)

2. **Read DEMO_SCRIPT.md** — the current script with the 6-act structure
   and dashboard cues.

3. **Identify the request type**:
   - **"Tighten act N"** → re-write the prose for that act, preserving
     the dashboard cues + wow moments.
   - **"Add a wow moment"** → write the new beat, position it in the
     arc (likely act 3 or 5), name the dashboard cue + audience-feel.
   - **"Rewrite the narration"** → bigger edit; preserve hard rules
     (verbatim thesis, conversation primitive, two wow moments).
   - **"What does this dashboard say"** → walk the script for any beat
     whose dashboard cue matches; quote the relevant lines.
   - **"Map beats to dashboards"** → produce a table:
     `act / beat / dashboard uid / specific panel / wow moment? (y/n)`.

4. **Update DEMO_SCRIPT.md** with the changes. Keep:
   - The 6-act structure (intro / OTel / conversations / economics /
     AI-optimizes-o11y / executive close).
   - Time budgets per act.
   - The "Hard rules for the script" section.
   - The "Open questions for tomorrow" list — append new questions; do
     not remove answered ones without confirmation.

5. **If the change implies a dashboard rebuild**, hand off to
   `ai-o11y-story-architect` with the specific beat the dashboard now
   needs to support. The architect should consume DEMO_SCRIPT.md to
   know which act/beat it's serving.

6. **If a wow moment is added or moved**, also update NARRATIVE.md's
   "Wow moments" section so the two stay synchronized.

## Hard rules

1. **The thesis sentence stays verbatim** in act 1:
   *"Observability optimized systems. Now observability is optimizing
   AI systems. And increasingly, AI is optimizing observability
   itself."*
2. **The conversation primitive framing stays verbatim** at first use:
   *"A conversation is the base unit of AI observability."*
3. **Two wow moments minimum.** The convo drill-down (act 3) and the
   missed-revenue chart lighting up (act 4). If a request implies
   cutting either, push back.
4. **Total time budget 7 min ± 45 s.** Tighten act 5 first if running
   long; protect acts 3 and 4.
5. **≤ 4 dashboard switches** across the whole script.
6. **Story is upstream of dashboards.** The script can demand a new
   dashboard; a dashboard cannot demand a new script.

## When the script changes, what else to update

| Change to DEMO_SCRIPT.md                                | Also update                                          |
|---------------------------------------------------------|------------------------------------------------------|
| Beat / wow moment added or moved                        | `NARRATIVE.md` "Wow moments" section                 |
| Dashboard cue changed                                   | `RATING.md` (re-rate the dashboard against its beat) |
| New dashboard implied                                   | Hand off to `ai-o11y-story-architect`                |
| Time budget restructured                                | Note in `CONTINUATION.md`                            |
| New framing or thesis                                   | `NARRATIVE.md` + `design_system.md`                  |

## Anti-patterns to refuse

- Rewriting in a way that loses one of the verbatim framings.
- Splitting wow moments across too many beats — both must be punchy.
- Letting an act run > 2 minutes (audience attention budget).
- Adding dashboards "just because" — they must serve a specific beat.
- Editing dashboards before the script is settled. **Story first.**

## Hand-off

When the script is satisfactory, identify which beats need dashboard
rebuilds and route each to `ai-o11y-story-architect`, then the rest
of the pipeline as usual.
