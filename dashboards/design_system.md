# ObserVIBElity dashboard design system

The look-and-feel contract for every curated dashboard in the `observibelity`
Grafana folder. Built on Grafana dark mode; refined into a polished "executive
demo" style that tells a business story instead of dumping metrics.

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

## Companion files

- **[`_design_tokens.py`](_design_tokens.py)** — Python constants for generators
- **[`_apply_ai_obs_aesthetic.py`](_apply_ai_obs_aesthetic.py)** — the last-step aesthetic pass
- **[`_rebuild_outage_cost.py`](_rebuild_outage_cost.py)** — reference implementation
