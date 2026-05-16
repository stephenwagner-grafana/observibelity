# ObserVIBElity dashboard design system

The look-and-feel contract for every curated dashboard in the `observibelity`
Grafana folder. Built on Grafana dark mode; refined into a polished "executive
demo" style that tells a business story instead of dumping metrics.

> **Read [`skills/NARRATIVE.md`](skills/NARRATIVE.md) first.** This file is
> the *visual half* of that narrative. The story is upstream of the visuals;
> the visuals serve the story.

> Generators should import [`_design_tokens.py`](_design_tokens.py) for the
> constants and run [`_apply_ai_obs_aesthetic.py`](_apply_ai_obs_aesthetic.py)
> as the last build step.

---

## 1. Story arc (every curated dashboard follows this order)

```
   Business impact   →   Customer impact   →   Technical cause   →   AI/model economics   →   Action
   ──────────────       ─────────────────       ───────────────       ─────────────────       ──────
   What did it cost?    Who was affected?       What broke?           Which models/tokens?    What now?
   $ / hour, run rate   journeys started        k3s / pod state       cost-per-cart, mix      runbook deeplinks
   missed revenue       carts abandoned         error gates           token / minute          alert routes
```

Every panel must belong to exactly one stage. Mixed-stage rows hurt the read.

---

## 2. Design tokens (single source of truth)

### 2.1 Color palette — *soft, restrained, intentional*

| Token             | Hex       | Used for                                       |
|-------------------|-----------|------------------------------------------------|
| `palette.blue`    | `#8AB8FF` | AI/model context, healthy headlines            |
| `palette.purple`  | `#A78BFA` | AI/model accents, attention without alarm      |
| `palette.pink`    | `#F472B6` | Risk, attention                                |
| `palette.orange` | `#FB923C` | Risk warning, projected cost                   |
| `palette.cyan`    | `#67E8F9` | Live/streaming series                          |
| `palette.mint`    | `#86EFAC` | Healthy / passing                              |
| `palette.rose`    | `#FCA5A5` | Soft failure                                   |
| `status.healthy`  | `#10B981` | "It's working" — only on green/red semantic stats |
| `status.warning`  | `#F59E0B` | Below target                                   |
| `status.danger`   | `#EF4444` | Outage, failure                                |
| `status.muted`    | `#9CA3AF` | Baseline lines, secondary labels               |

**Rule of intentional color**: choose one of these tracks per panel —
- **soft palette** (blue→purple→pink→orange) when ranking, distributing, mixing models
- **status palette** (green/amber/red) when something is "healthy / risk / broken"

Never both in the same panel. Never neon.

### 2.2 Per-model color pins

Every chart that breaks down by model uses the same hue per model:

| Model                       | Color                  |
|----------------------------|------------------------|
| `claude-opus-*`             | `palette.purple` (or lighter violet for variants) |
| `claude-sonnet-*`           | `palette.blue`         |
| `claude-haiku-*`            | `palette.cyan`         |
| `gemma2:*`                  | `palette.mint`         |
| `llama3.*` / `qwen3:*`      | `palette.pink` / `palette.rose` |
| `tinyllama:*` / `phi3:*`    | warm yellow / `palette.orange` |
| `anthropic` aggregate        | `palette.pink`         |
| `ollama` aggregate           | `palette.cyan`         |

Series labelled `loadgen`, `live`, `pass`, `fail`, `< 80`, `80+` are also pinned.
See `MODEL_COLOR_PINS` in `_apply_ai_obs_aesthetic.py`.

### 2.3 Typography (Grafana defaults, with hierarchy)

| Token        | Use                                                       |
|--------------|-----------------------------------------------------------|
| `hero`       | Big-number stat panels (≥ 8w × 8h). Center-aligned, value mode "value", background color. |
| `kpi`        | Secondary stats (4w × 4h). Center-aligned, value mode "value", no background. |
| `helper`     | Description sub-text. Markdown inline italics, muted color. |
| `row-header` | Emoji + 1–2 word topic + 6–10 word what-this-row-says.   |

### 2.4 Spacing & layout

| Token            | Value | Use                                                  |
|------------------|-------|------------------------------------------------------|
| `grid.cols`      | 24    | Full row width                                       |
| `row.header.h`   | 1     | Always 1                                             |
| `hero.w`         | 12    | Half-row                                             |
| `hero.h`         | 8     | Full hero height                                     |
| `kpi.w`          | 6     | Quarter-row                                          |
| `kpi.h`          | 4     | Half hero height                                     |
| `state.timeline.h` | 7   | One row of state timeline                            |
| `chart.h`        | 8     | Standard timeseries / barchart                       |
| `chart.h.tall`   | 9–10 | When showing stacked-by-model series                 |
| `text.callout.h` | 8     | Explainer text alongside a hero                      |
| `roi.text.h`     | 10    | ROI table at the bottom                              |

### 2.5 Units (the "human-scaled" rule)

| Magnitude          | Unit choice                                                  |
|--------------------|--------------------------------------------------------------|
| Hourly revenue     | `currencyUSD` — auto-K/M suffixes are fine                    |
| Per-token cost     | `$/1M tokens` (set custom suffix) — *never* `$/token`        |
| Per-call rate      | `calls/min` (= rate × 60)                                    |
| Per-hour rate      | `$/hr` (= rate × 3600)                                       |
| Token throughput   | `tokens/min`                                                 |
| Latency            | `ms` (Grafana `ms`)                                          |
| Quality / capture  | `percent` with decimals = 1                                  |
| Pure count w/ unit | `unit: "none"` + `customUnit: " carts/hr"` (leading space)   |

Pick the unit *after* eyeballing the typical value range — defaults are
starting points. If the glance test fails ("is that big or small?"), override.

### 2.6 Radii, shadows, opacity (panel-level)

Grafana doesn't expose per-panel CSS, so these manifest as JSON conventions:

| Token              | Encoded as                                                  |
|--------------------|-------------------------------------------------------------|
| `panel.radius`     | Default Grafana panel chrome — do NOT set `transparent: true` on regular panels |
| `panel.elevated`   | Hero panels use `colorMode: "background"` for the soft glow |
| `chart.fill.opacity` | timeseries lines: 30; bars: 90–95; stacked bars: 95       |
| `bar.width.factor` | 0.92–0.96 (just-enough gap between bars)                    |
| `ribbon.opacity`   | The top sparkline ribbon stays `transparent: true`          |

---

## 3. Visual language rules (when to use what)

### 3.1 Picking the right panel type

| Data shape                           | Panel              |
|--------------------------------------|--------------------|
| Single headline value                | `stat` (hero or kpi) |
| Trend over time                      | `timeseries` (smooth line, low fill) |
| Per-time-bucket totals (revenue, $cost) | `timeseries` with `drawStyle: "bars"`, `step: 10m`, stacked by category if useful |
| Ranking / contribution               | `bargauge` (horizontal, gradient) |
| Up/down/known states over time       | `state-timeline` with value mappings |
| Decision-making list                 | `table` — sparingly. No raw dumps. |
| Composition at-a-glance              | `piechart` (donut) — sparingly |
| Section divider                      | `row` with collapsed default |

### 3.2 Picking the color track

| Panel intent                            | Track     |
|----------------------------------------|-----------|
| Healthy / unhealthy state              | `status` (green/amber/red) |
| "Pass / fail" eval                     | `status`  |
| Revenue made                           | `palette.cyan` or `status.healthy` |
| Revenue missed / projected loss        | `status.danger` (pink for soft, red for sharp) |
| Token / cost                           | `palette.blue` → `palette.orange` percentage gradient |
| Models compared                        | per-model pin (`MODEL_COLOR_PINS`) |
| Outage signal                          | `status.danger` |
| Customer journey                       | `palette.cyan` healthy, `status.danger` blocked |

### 3.3 Hero vs. KPI emphasis

The **most important panel in each row** must be visually dominant:
- Hero: `w ≥ 12`, `h = 8`, `colorMode: "background"`, big number centered
- KPIs: `w = 4–6`, `h = 4`, `colorMode: "value"`, smaller number
- If a row has two heroes, they're side by side at `8w × 8h` each (with a 8w callout between or beside)

### 3.4 Numbers must be "human-relatable"

Before shipping a stat, sanity-check it against this:

- ✅ "$24K/hr" / "$905K today" / "92% capture" / "3 hours"
- ❌ "0.00041 cart-adds/second" / "$143,419,250" / "3.0 hour" / "360 events"

Fixes:
- **Wrong unit** → swap (`$/sec` → `$/hr`; `events` → `carts/hr`; `$/token` → `$/1M tokens`)
- **Exponential value** → use Grafana's auto-K/M, and add a plain-English subtitle ("if today repeats every day for a year")
- **Mismatched decimals** → use `0` for $K/M; `1` for percent; `0` for counts

### 3.5 Section headers ("rows")

Row title pattern: **`<emoji> <topic> — <what this row tells you>`**

- ✅ `💰 Revenue right now — what the engine is making`
- ✅ `🛑 Cost if the engine stops — what an outage costs the business`
- ❌ `Revenue` (too terse)
- ❌ `Cost / outage / SLA / projection panel` (slash salad)

### 3.6 Story-arc-friendly insight cards

For "this is why this dashboard pays for itself" or "how to read these numbers"
moments, use a markdown `text` panel positioned next to a hero, like a callout
card. Pattern:

```markdown
### <H3 with emoji>

<single short paragraph in plain English>

<one optional sub-paragraph with the *why*>

> <pull-quote with the actionable nudge>
```

No code blocks, no math equations. Embed variables as plain dollar amounts:
`$${avg_atc_value}` not ``` `${avg_atc_value}` ```.

---

## 4. Pre-ship checklist (Claude runs through this before pushing a dashboard)

Copy/paste this into the rebuild script's docstring. Tick every box.

### Story
- [ ] Dashboard tells one story top-to-bottom (no detour rows)
- [ ] Row order follows: business impact → customer impact → technical → AI/model → action
- [ ] Every row title has an emoji + 1-line "what this row says"
- [ ] Total panel count ≤ ~25; if more, split into a sibling dashboard

### Hero
- [ ] Each row has one dominant panel (`w ≥ 12, h = 8`)
- [ ] Hero uses `colorMode: "background"` with a soft palette / status color
- [ ] Hero title uses dynamic variable interpolation where it helps ("A 3-hour outage costs")
- [ ] Hero has a `noValue` fallback (`"$0"` or `"—"`)

### Numbers
- [ ] Every stat eyeballs as human-relatable ($K/$M, percent, hours, carts/hr)
- [ ] No `$/token`; use `$/1M tokens`. No `events/sec`; use `calls/min` or `$/hr`
- [ ] No `3.0 hour` — use `customUnit: " hours"` for unitless integers with a suffix
- [ ] Stat panels use `instant: true` for short-window queries to avoid "No data" flicker

### Color
- [ ] One track per panel (status or palette, not both)
- [ ] Per-model series use the `MODEL_COLOR_PINS` overrides
- [ ] Negative-direction series (missed, lost, errors) → red/pink; positive → green/cyan
- [ ] No `palette-classic` rainbow on quantitative comparisons

### Queries / data
- [ ] Datasources pinned via `${datasource_loki}` / `${datasource_prom}` (never default)
- [ ] No `clamp_min` in LogQL (not supported on this tenant)
- [ ] No `$__rate_interval` in LogQL (not supported on this tenant) — use a literal like `[1m]`
- [ ] 10-min-bucket bars use `step: "10m"` (non-overlapping windows)
- [ ] Annotations cover: pod restarts, k3s NotReady, deploys

### Aesthetic application
- [ ] Final step: `python3 dashboards/_apply_ai_obs_aesthetic.py dashboards/<file>.json`
- [ ] Ribbon panel (`id=100`) at `y=0`, height 3, transparent
- [ ] All other panels `transparent: false` (so they read as elevated cards)
- [ ] Tables: no full-bright thresholds; softened palette only

### Variables
- [ ] Variables at the top use plain-English labels ("Avg cart-add value ($)" not "avg_atc_value")
- [ ] Money tunables default to round numbers (`150`, `360`, `8760`)

### Empty states
- [ ] Stat panels: `noValue: "$0"` so empty windows don't blank the panel
- [ ] Annotations don't fire spuriously on warm-up data

---

## 5. The "premium" small-things checklist

Hard to define, easy to spot. Before shipping:

- [ ] Margins feel consistent (don't mix `h=7` and `h=8` in the same row)
- [ ] Description text on every non-row panel — the `(i)` tooltip carries half the story
- [ ] Markdown callout panels are `transparent: true` (so they read as page text, not a card)
- [ ] Pre-existing dashboards in the folder open without a single "No data" panel
- [ ] The top ribbon scrolls fluidly even at refresh = 30s
- [ ] Annotation markers are subtle (orange/red, dashed, not solid bars)
- [ ] Legend sort order is deliberate (by Total desc, not alphabetical)

---

## 6. Don'ts

- Don't use neon green, hot pink, electric blue
- Don't render tables with full-saturation cell backgrounds (blinding)
- Don't render every panel `transparent: true` (loses the card structure)
- Don't break the story arc to fit a panel that "looks cool"
- Don't pile more than 3 series into a stacked area
- Don't put hero numbers next to a sparkline if the data is too sparse for the sparkline
- Don't ship a dashboard without running `_apply_ai_obs_aesthetic.py`
- Don't write multi-paragraph helper text — one line, one sentence

---

## 7. Semantic panel taxonomy

Every panel on a curated dashboard MUST identify with one of these named
**semantic kinds**. The kind drives palette, sizing, calc, and lint rules.
Rebuild scripts should set `panel.title` and use the matching `SIZE` and
`UNIT` constants from `_design_tokens.py`.

| Kind                    | Story stage   | Typical panel type | Size      | Color track | Notes                                                              |
|-------------------------|---------------|--------------------|-----------|-------------|--------------------------------------------------------------------|
| `revenue.hero`          | business      | stat               | 12w × 8h  | status      | One per "revenue right now" row. `colorMode: background`.          |
| `revenue.kpi`           | business      | stat               | 6w × 4h   | status      | Supporting headline (24h total, run rate, etc.).                   |
| `revenue.flow.actual`   | business      | timeseries (bars)  | 24w × 9h  | per-model   | 10-min buckets stacked by model; `step: "10m"`.                    |
| `revenue.flow.missed`   | business      | timeseries (bars)  | 24w × 8h  | status      | Same 10-min step; single danger color; only fires when error gate. |
| `journey.health`        | customer      | state-timeline     | 12w × 7h  | status      | 0/1 strip with value mappings (locked-out / can shop).             |
| `journey.start_vs_end`  | customer      | bargauge / table   | 12w × 8h  | per-model   | "Started journeys" vs "completed checkouts" by persona/model.      |
| `journey.abandoned`     | customer      | stat               | 6w × 4h   | status      | Count or % of journeys that errored before checkout.               |
| `engine.state`          | technical     | state-timeline     | 12w × 7h  | status      | k3s nodes / critical pods Ready state.                             |
| `engine.errors_table`   | technical     | table              | 24w × 8h  | status      | Top firing alerts. Soft palette, no full-saturation cells.         |
| `engine.deploys`        | technical     | annotations layer  | n/a       | muted       | Deploys + restarts shown as vertical markers across the day.       |
| `ai.cost_per_call`      | ai economics  | stat               | 6w × 4h   | soft        | `$/call` rolled up; unit = currencyUSD, decimals=4 if < $0.10.     |
| `ai.cost_per_mtoken`    | ai economics  | bargauge           | 12w × 8h  | soft        | `$/1M tokens` per model. Gradient blue → orange.                   |
| `ai.token_flow`         | ai economics  | timeseries (bars)  | 24w × 9h  | per-model   | tokens/min stacked by model.                                       |
| `ai.model_mix`          | ai economics  | bargauge           | 12w × 8h  | per-model   | Share of calls/tokens by model (24h).                              |
| `ai.judge_pass_rate`    | ai economics  | stat               | 6w × 4h   | status      | Eval/judge pass rate %.                                            |
| `action.runbook`        | action        | text (markdown)    | 24w × 10h | none        | The "what to do now" block. ROI math, links to runbooks/alerts.    |
| `action.alert_routes`   | action        | table              | 24w × 6h  | status      | Routes + on-call rotation. Sparingly decorated.                    |
| `header.ribbon`         | (all)         | timeseries (bars)  | 24w × 3h  | soft        | `transparent: true`. The top accent strip.                         |
| `header.row`            | (all)         | row                | 24w × 1h  | n/a         | Emoji-prefixed section title.                                      |
| `callout.insight`       | (any)         | text (markdown)    | 8w × 8h   | none        | `transparent: true`. Plain-English story beside a hero.            |
| `welcome.title`         | (welcome)     | text (markdown/html)| 24w × 6h | soft        | Large hero block: title + subtitle. Centered. `transparent: true`. |
| `narrative.thesis`      | (welcome)     | text (markdown/html)| 24w × 5h | none        | Single load-bearing thesis statement. Centered, italic. `transparent: true`. |
| `narrative.spectrum`    | (welcome)     | text (html gradient)| 6w × 4h | soft (canonical gradient) | One shift-left axis with two endpoint labels and a CSS gradient bar. |
| `narrative.signal_stack`| (welcome)     | text (html)        | 24w × 9h  | soft        | MLTPC fork diagram visualizing OTel signals + the fifth (conversations) branching from traces. |
| `narrative.singularity` | (welcome)     | text (html)        | 16w × 8h  | soft        | The drill-down preview: conversation, trace, tool call, db error, sql, with arrows between. |
| `nav.card`              | (action)      | text (markdown)    | 4w × 6h   | soft (one per card) | Clickable card linking to a child dashboard. |
| `nav.axis`              | (action)      | text (html gradient)| 24w × 2h | soft (canonical gradient OR locally inverted, see note) | Gradient bar under a row of nav.cards, with endpoint labels that telegraph the conceptual axis. |

The `welcome.*`, `narrative.*`, and `nav.*` kinds are used by the `welcome-screen` archetype (§8.6). They are narrative panels with no underlying query, sized for visual rhythm rather than for data density. The lint rules `hero.too-small` and `color.mixed-tracks` are downgraded to INFO for these kinds because the typical row in a `welcome-screen` dashboard is composed of four to six equal-sized panels rather than a single hero plus supports.

**Rule of one kind per panel** — `panel.description` SHOULD start with the
kind in brackets so the linter can parse it: `[revenue.hero] What the
engine is making right now.` This is optional in v1 but required for the
strict linter mode.

---

## 8. Dashboard archetype catalog

Named layouts. When asked to build a dashboard, pick the archetype first;
then the layout composer fills in the rows from the panel taxonomy.

### 8.1 `outage-impact` — the headline business dashboard

Used for: **outage cost, executive demo**. Reference: `ai-obs-outage-cost`.

```
y=0   header.ribbon                                      24w × 3h
y=3   ⟨header.row⟩ 💰 Revenue right now                  24w × 1h
y=4   revenue.hero (12w) | revenue.kpi×4 (12w stacked)    24w × 8h
y=12  ⟨header.row⟩ 📉 Missed revenue today               24w × 1h
y=13  revenue.kpi×5 row                                   24w × 8h
y=21  ⟨header.row⟩ 🛑 Projected outage cost              24w × 1h
y=22  callout.insight | revenue.hero | revenue.kpi×4    24w × 8h
y=30  ⟨header.row⟩ 📈 When the engine ran vs. stopped    24w × 1h
y=31  engine.state | journey.health                       24w × 7h
y=38  ⟨header.row⟩ 📊 Revenue per 10-minute block        24w × 1h
y=39  revenue.flow.actual (stacked by model)              24w × 9h
y=48  revenue.flow.missed                                 24w × 8h
y=56  ⟨header.row⟩ 🤖 AI model economics                 24w × 1h
y=57  ai.model_mix | ai.cost_per_mtoken                   24w × 8h
y=65  ⟨header.row⟩ 💡 Why this pays for itself           24w × 1h
y=66  action.runbook                                      24w × 10h
```

### 8.2 `per-user-attribution` — "who's costing us money?"

Used for: **per-user cost analysis, FinOps view**. Reference: `ai-obs-cost`.

```
header.ribbon
⟨🧑 Who's spending right now⟩
   journey.start_vs_end | revenue.kpi (top spender / top abuser)
⟨📊 Cost per user — 24h leaderboard⟩
   ai.cost_per_call (per-user table, 24w)
⟨🤖 What models are they running⟩
   ai.model_mix | ai.cost_per_mtoken
⟨💡 Action⟩
   action.runbook (with redirect routes)
```

### 8.3 `app-overview` — landing page for one app (e.g. NeonCart)

Used for: **app-level demo entry**. Reference: `ai-obs-app-neoncart`.

```
header.ribbon
⟨💰 What the app is making⟩
   revenue.hero | revenue.kpi×3
⟨💬 Conversations & specialists⟩
   journey.start_vs_end (the convo bar chart) | ai.judge_pass_rate
⟨🤖 Model mix & cost⟩
   ai.model_mix | ai.cost_per_mtoken | ai.token_flow
⟨📈 Healthy operation⟩
   engine.state | engine.errors_table
⟨💡 Action⟩
   action.alert_routes
```

### 8.4 `eval-quality` — judge results and toxicity

Used for: **evaluator dashboards, quality monitoring**. Reference: `ai-obs-evals`.

```
header.ribbon
⟨🎯 Today's quality⟩
   ai.judge_pass_rate (hero) | revenue.kpi (eval volume)
⟨📊 Pass / fail by judge⟩
   bargauge (per judge, stacked by pass/fail)
⟨🤖 Per-model quality⟩
   ai.model_mix (recolored by pass/fail) | table per-model breakdown
⟨💡 Action⟩
   action.runbook (link to failing examples)
```

### 8.5 `landing` — folder-level navigator

Used for: **directory of dashboards within a folder**. Reference: `ai-obs-app-landing`.

```
header.ribbon
N × big rectangular "card" text panels, each linking to a dashboard.
No data queries. Pure navigation.
```

### 8.6 `welcome-screen`: opener dashboard, used in place of slides

Used for: **opening dashboard of a story presentation, first-screen agenda**. Reference: `ai-obs-welcome`.

A hybrid of `landing` (folder navigator) and a narrative explainer. Replaces the opening slides of a presentation with a live dashboard. Mirrors the OOTB Grafana AI Observability landing page (hero block at top + KPI strip at bottom) with narrative content cards in between.

The substitute story arc for `welcome-screen` is:
**Establish → Provoke → Teach (concept) → Teach (concept) → Forecast (action) → Ground in data**.

Canonical layout:

```
y=0   header.ribbon                                                 24w × 3h
y=3   welcome.title                                                 24w × 6h
y=9   narrative.thesis                                              24w × 5h
y=14  ⟨header.row⟩ 🧭 The four spectra. ...                         24w × 1h
y=15  narrative.spectrum × 4                                         24w × 4h (6w each)
y=19  ⟨header.row⟩ 🔭 The fifth signal. ...                          24w × 1h
y=20  narrative.signal_stack                                         24w × 9h
y=29  ⟨header.row⟩ 🧶 The singularity. ...                           24w × 1h
y=30  narrative.singularity | callout.insight                       24w × 8h (16w + 8w)
y=38  ⟨header.row⟩ 🗺 The path ahead. ...                            24w × 1h
y=39  nav.card × 5                                                  20w × 6h (4w each, 2w lead + 2w trail)
y=45  nav.axis                                                      24w × 2h
y=47  ⟨header.row⟩ 📊 Highlights from the last 24 hours. ...         24w × 1h
y=48  stat × 6                                                      24w × 4h (4w each)
```

Total height: 52.

Pre-ship checklist additions (in addition to §4):
- [ ] No em dashes (U+2014) in any panel title, description, or markdown content. Use periods, commas, parentheses, or colons.
- [ ] No words "Demo", "use case", or "load gen" anywhere visible.
- [ ] At least one KPI in the bottom strip has `colorMode: "background"` to act as the hero of the row (size is held equal across the strip for visual rhythm).
- [ ] Nav cards 1-5 link to actual child dashboards (titles + URLs filled in before the demo, not placeholders).

### Picking an archetype

| If the brief says…                              | Archetype              |
|-------------------------------------------------|------------------------|
| "outage cost / lost revenue / SLA impact"       | `outage-impact`        |
| "who's the most expensive user"                 | `per-user-attribution` |
| "show me how NeonCart / SupportBot is doing"    | `app-overview`         |
| "is the LLM giving good answers"                | `eval-quality`         |
| "I just want a landing page"                    | `landing`              |
| "an opener / agenda / welcome to <story>"       | `welcome-screen`        |

---

## 9. Lint rules spec

Enforced automatically by [`dashboard_lint.py`](dashboard_lint.py). Three
severity levels: **ERROR** (must fix before push), **WARN** (should fix),
**INFO** (nudge).

### Story-arc rules

- **ERROR `arc.row-order`** — row titles must follow the canonical 5-stage
  order. Custom rows are allowed but must declare their stage via the row
  title's emoji (`💰`, `👥`, `📈`, `🤖`, `💡` — one of the five canonical
  emojis). Out-of-order rows are an ERROR.
- **WARN `arc.missing-action`** — every dashboard SHOULD end with a `💡 …`
  action row.
- **INFO `arc.too-long`** — > 7 rows on a single dashboard suggests it
  should be split.

### Hero rules

- **ERROR `hero.too-small`** — first non-row panel under a row header
  MUST be `w ≥ 12` and `h ≥ 8` if its type is `stat` and its title doesn't
  contain "tunable" / "ref".
- **WARN `hero.no-color-mode`** — the hero stat SHOULD set
  `options.colorMode = "background"`.
- **WARN `hero.no-description`** — every stat panel needs a description.

### Color rules

- **ERROR `color.rainbow-on-quantitative`** — any panel with
  `color.mode = "palette-classic"` AND `type` in {timeseries, bargauge,
  barchart, table} is ERROR (use thresholds or `palette-classic-by-name`).
- **WARN `color.mixed-tracks`** — if thresholds steps mix soft palette
  hexes (`#8AB8FF`, `#A78BFA`, etc.) AND status palette hexes (`#10B981`,
  `#EF4444`), WARN.
- **INFO `color.model-pin-missing`** — if a query has `legendFormat`
  matching a known model name and no `byName` override pinning its color,
  INFO suggest the pin.

### Unit rules

- **WARN `unit.exponential`** — any stat whose default unit is `short` or
  blank AND whose typical value > 1e6, WARN to suggest currencyUSD /
  customUnit.
- **WARN `unit.per-token`** — any unit string containing `/token` (without
  the `/1M` prefix), WARN.
- **WARN `unit.degenerate-hours`** — `unit: "h"` shows `"3.0 hour"`; WARN
  to use `customUnit: " hours"` instead.

### Empty-state rules

- **WARN `query.flicker-risk`** — stat panel + Loki target with `[1h]` or
  `[5m]` range AND `range: true` (instead of `instant: true`), WARN to
  set `instant: true` + `noValue`.
- **INFO `query.no-novalue`** — stat panel without a `fieldConfig.defaults.noValue`,
  INFO.

### Tenant-specific rules

- **ERROR `loki.clamp-min`** — LogQL queries using `clamp_min(...)` ERROR
  (not supported on this tenant).
- **ERROR `loki.rate-interval-var`** — LogQL queries using
  `$__rate_interval` ERROR (use literal `[1m]`).

### Aesthetic-pass rules

- **ERROR `aesthetic.no-ribbon`** — first panel must be `id=100`
  (the ribbon) or there must be a panel at `y=0, h=3` that's transparent.
- **WARN `aesthetic.transparent-panel`** — non-ribbon non-callout panel
  with `transparent: true` is WARN (loses the elevated card feel).

### Archetype exemptions

- **INFO `arc.welcome-screen-relaxed`**: when the dashboard's archetype is `welcome-screen` (detected by uid starting with `ai-obs-welcome` OR by presence of any `welcome.*` or `narrative.*` panel kind), the rules `hero.too-small`, `color.mixed-tracks`, and `arc.row-order` are downgraded to INFO. The welcome-screen archetype favors visual rhythm over a dominant hero per row.

The linter should also exempt panel kinds prefixed with `welcome.`, `narrative.`, `nav.` from the `hero.no-color-mode`, `hero.no-description` rules (these are narrative panels without queries, so the description rule doesn't apply uniformly).

### Running the linter

```bash
python3 dashboards/dashboard_lint.py dashboards/ai-obs-outage-cost.json
# exit code 0 = clean / WARN-only; non-zero = at least one ERROR
```

The linter is the LAST step before `dashboards-sync.sh push`. CI should
fail if any ERROR fires.

---

## 10. Conceptual primitives (the framings that drive the visuals)

These are the load-bearing ideas from
[`skills/NARRATIVE.md`](skills/NARRATIVE.md). Every dashboard ultimately
illustrates one or more of these. If a panel can't be traced back to one
of these primitives, ask whether it belongs in the demo at all.

### 10.1 The four primitives of observability

Classical o11y has three primitives. AI o11y adds a fourth.

| Primitive            | Atomic unit                    | Where you see it in dashboards |
|----------------------|--------------------------------|--------------------------------|
| **Metric datapoint** | a scalar at an instant         | every `stat` and `timeseries` panel |
| **Log line**         | a structured text event        | Loki queries, log-derived counts (e.g. ATC events) |
| **Span**             | a unit of work in a trace      | OTel + Tempo deep-links |
| **Conversation**     | a semantic execution graph     | every panel that drills into a conversation row — the convo bar charts, journey panels, eval breakdowns |

A **conversation** has: prompts, tools, evals, tokens, model decisions,
traces, user intent, business outcomes. Every AI o11y dashboard should
have *at least one panel* where the audience can see "this is a
conversation, not just data." If your dashboard doesn't, you may be
visualizing logs in disguise.

### 10.2 The shift-left axis

There is a single conceptual axis that runs through everything:

```
   LEFT                                                    RIGHT
   ─────────────────────────────────────────────────────────────
   subjective                                          objective
   experimental                                        production
   dev                                                 prod
   non-deterministic                                   deterministic
```

**The job of AI o11y is to move things rightward** — turn ambiguous AI
behavior into measurable operational systems. Treat the four axes as
correlated; reach for the same vocabulary across panels.

Visually, the shift-left motion should appear as a recurring motif —
the existing soft-palette ribbon (blue → purple → pink → orange) doubles
as a "subjective → objective" gradient and can be reused as an
intentional cue.

### 10.3 The recursive loop

The demo's punchline is recursion:

1. **classical o11y → systems get healthier** (the old story)
2. **o11y → AI systems get healthier** (the new frontier — this demo)
3. **AI in o11y → observability itself gets smarter** (the recursive payoff)

The dashboards collectively should make all three loops visible: the
traditional RCA panels (loop 1), the AI-economics + conversation panels
(loop 2), and the AI-assisted-investigation panels (loop 3). A dashboard
that supports only one loop is fine; one that obscures the recursion is
a problem.

### 10.4 Verbatim framings (quote these, don't paraphrase)

- "A conversation is the base unit of AI observability."
- "AI changes the nature of telemetry itself."
- "Observability optimized systems; now it optimizes AI."
- "Using AI to optimize observability, while using observability to optimize AI."
- "Shift-left turns subjective AI behavior into measurable operational systems."
- "Observability is the control plane for AI systems." *(strategic close — supersedes the earlier "operating system" phrasing)*

These appear in `NARRATIVE.md` and the spoken `DEMO_SCRIPT.md`. The
design system's job is to make sure the visuals don't undercut them.

### 10.5 The 97.7% callback (narrative motif → visual requirement)

The demo's cold open is a concrete dollar number: *7.6M tokens of
inference would cost $114 on Claude Sonnet but $2.67 locally — a 97.7%
reduction*. Act 4 pays it back by comparing $2.67 (day of AI) to ~$47K
(45 seconds of outage). The callback is the demo's financial spine.

**Visual requirement**: `ai-obs-outage-cost` should surface the
cost-savings ratio (or at least the local-marginal-vs-equivalent-Claude
$ comparison) as a small KPI visible in Act 4. Without it, the
callback is verbal-only and weaker. *(Implementation pending — flagged
in `DEMO_SCRIPT.md` open questions and `CONTINUATION.md`.)*

### 10.6 The path-ahead axis (cards vs. gradient)

When a `welcome-screen` dashboard uses `nav.card × 5` plus `nav.axis` to preview an upcoming sequence of dashboards, two color conventions can apply:

| Convention | Gradient direction | When to use |
|---|---|---|
| **Design-system canonical** | Cool (blue) on left, warm (orange) on right, matching the soft-palette ribbon. Label LEFT as "subjective / probabilistic", RIGHT as "objective / deterministic". | Default. Visually rhymes with the ribbon at top of every dashboard. |
| **Locally inverted (card-aligned)** | Warm on left, cool on right. Labels LEFT as "deterministic / objective", RIGHT as "subjective / probabilistic". | Used when card 1 (the narrative starting point, conceptually deterministic) is positioned at the LEFT end of the row. Picks local coherence (card position = label) over global ribbon convention. |

The choice is per-dashboard. Document the choice in the `nav.axis` panel description.

---

## Companion files

- **[`skills/NARRATIVE.md`](skills/NARRATIVE.md)** — the *vision* (read first)
- **[`skills/DEMO_SCRIPT.md`](skills/DEMO_SCRIPT.md)** — the *spoken script*
- **[`_design_tokens.py`](_design_tokens.py)** — Python constants for generators
- **[`_apply_ai_obs_aesthetic.py`](_apply_ai_obs_aesthetic.py)** — the last-step aesthetic pass
- **[`_rebuild_outage_cost.py`](_rebuild_outage_cost.py)** — reference implementation of the `outage-impact` archetype
- **[`dashboard_lint.py`](dashboard_lint.py)** — automated linter
- **[`skills/README.md`](skills/README.md)** — index of the 6 Claude skills that drive the lifecycle
