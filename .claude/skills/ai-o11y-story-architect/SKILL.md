---
name: ai-o11y-story-architect
description: Turn a one-line dashboard brief into a story arc + archetype pick + hero metrics. Use when the user says "design a dashboard for X", "build me a dashboard about Y", "what would a dashboard for Z look like", or before any new dashboard work. Returns a structured plan (archetype, rows, hero metrics, emotional beats) that downstream skills consume. Never writes JSON.
allowed-tools: Read, Grep, Glob
---

# ai-o11y-story-architect

The first step in the ObserVIBElity dashboard lifecycle. Turns a fuzzy
brief into a concrete story plan.

## When to trigger

When the user says ANY of:
- "Design a dashboard for…"
- "Build me a dashboard about…"
- "What would a dashboard for X look like?"
- "I want a demo dashboard that shows…"

OR when **any** of the other ai-o11y-* skills are about to start work and
no story plan exists yet for the dashboard at hand.

## What this skill does NOT do

- Does not write JSON or Python (that's `ai-o11y-grafana-builder`)
- Does not pick panel positions (that's `ai-o11y-layout-composer`)
- Does not apply colors (that's `ai-o11y-aesthetic-pass`)
- Does not score (that's `ai-o11y-dashboard-critic`)

## Procedure

1. **Read the design system** at `dashboards/design_system.md` — sections
   §1 (story arc), §8 (archetypes), §7 (semantic panel taxonomy).

2. **Clarify the brief** with the user, but no more than 3 questions:
   - **Audience**: CFO / SRE / Eng / Mixed?
   - **Time horizon**: real-time, today, trailing-7d, all-time?
   - **One-sentence elevator pitch**: "this dashboard shows…"

3. **Pick the archetype** from §8 of the design system:
   - outage / SLA / business cost → `outage-impact`
   - cost-per-user, per-team, per-app → `per-user-attribution`
   - "how is X doing" for one app → `app-overview`
   - evals / hallucinations / quality → `eval-quality`
   - folder index → `landing`

4. **Identify the 5 story-arc stages** for this dashboard:
   - **Business impact**: the headline $ number — what does the reader
     care about in 5 seconds?
   - **Customer impact**: who hurts when this is broken — name them
     (personas, customer segments, journey types).
   - **Technical cause**: what k8s / pod / cluster signal explains it?
   - **AI/model economics**: which model(s) drive cost / quality here?
   - **Action**: where does the reader click next?

5. **Choose hero metrics** — one per row:
   - Each must be **human-relatable** (`$/hr`, `carts/hr`, percent, ms,
     `$/1M tokens` — see §2.5 of the design system).
   - Pair each with a **plain-English subtitle** the description tooltip
     will display.

6. **Define emotional beats** — for a demo, note where the audience should
   feel something:
   - "the $ number lands"
   - "the red bars show outage damage"
   - "the model mix reveals the cost driver"
   - "the action block tells them what to do"

7. **Output the plan** as a single markdown block in this shape:

```markdown
# Story plan: <dashboard-uid>

**Archetype**: <one of: outage-impact, per-user-attribution, app-overview, eval-quality, landing>
**Audience**: <CFO / SRE / Eng / Mixed>
**Elevator pitch**: <single sentence>

## Rows (in canonical 5-stage order)

### 1. 💰 Business impact — <row sub-title>
- **Hero metric**: <name> (`<unit>`) — <plain-English description>
- **Supporting KPIs**: <comma-separated list>
- **Beat**: <what the audience should feel>

### 2. 👥 Customer impact — <row sub-title>
- (same fields)

### 3. 📈 Technical cause — <row sub-title>
- (same)

### 4. 🤖 AI/model economics — <row sub-title>
- (same)

### 5. 💡 Action — <row sub-title>
- **Content**: <runbook block + alert routes + deep-links>
- **Beat**: "they know what to do now"
```

8. **Hand off** to `ai-o11y-layout-composer` for sizing/positioning, or to
   `ai-o11y-grafana-builder` directly if the user is impatient (the
   composer step is optional for archetypes that already have a baked
   layout).

## Anti-patterns to refuse

- Story plans that skip a stage. If the dashboard "doesn't need an
  Action row", push back — every demo dashboard needs one.
- Hero metrics that aren't human-readable (`events/sec`, `0.00041 carts`,
  `1.4e7 tokens` — fix the unit *before* writing the plan).
- More than one hero per row. If the user pitches two co-equal
  headlines, ask which one matters more.
- More than 6 rows. If the brief naturally exceeds, propose splitting
  into two sibling dashboards.

## Memory + docs to consult

- `dashboards/design_system.md` (canonical)
- `MEMORY.md` → `observibelity/design_system.md`
- `dashboards/RATING.md` (to learn from past dashboards' weak points)
- `dashboards/skills/CONTINUATION.md` (any prior in-flight work)
