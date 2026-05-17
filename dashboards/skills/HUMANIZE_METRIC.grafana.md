# Humanize metric values — Grafana Assistant skill body

> **To install in Grafana Cloud**: open the Assistant (✨ icon), say
> "Create a skill called *Humanize Metric Values* with these instructions:",
> then paste **everything below the next horizontal rule**.
>
> Re-paste whenever this file changes. The canonical source is
> `dashboards/skills/HUMANIZE_METRIC.md` in the observibelity repo; this
> file is a stripped, self-contained re-flow with no repo-path references.

---

# Skill — Humanize Metric Values

## Purpose

When a dashboard panel's value fails the glance test — sub-1 rates,
scientific notation, opaque per-token costs, raw byte counts — re-frame
the metric so a non-expert reads the magnitude correctly in five seconds.

Trigger this skill whenever the user says:
- "What's the right unit for this?"
- "This number reads weird / has too many zeros."
- "Humanize this panel."
- "How would a CFO read this?"
- "Why is this displayed as 0.000003?" / "Why is this 0.03 per hour?"

Or whenever you're about to build a panel whose typical value isn't
already in the 1–999 range with a recognizable unit.

## The three humanization modes

Try them in order. The first that produces a numerator in **1–999** AND
a denominator the audience already cares about wins. If none does, fall
through to mode 3 (analogy).

### Mode 1 — Unit-family / SI scaling

Mechanical. If the unit has standard prefixes or conversions, walk the
ladder until the value lands in 1–999.

- `1500 ms` → `1.5 s`
- `1.2e9 bytes` → `1.2 GB`
- `0.041 s` → `41 ms`
- `1500000 tokens` → `1.5M tokens`
- `4300 W` → `4.3 kW`

If mode 1 works, stop.

### Mode 2 — Denominator rebasing

When the metric is a rate or ratio with a tiny numerator. Replace
`X per second` with `Y per <thing the audience cares about>`.

- `0.03 ATCs/hour` → **"3 ATCs per 100 customers"**
- `0.000003 $/token` → **"$3 per 1M tokens"**
- `0.0001 errors/sec` → **"1 error per 10,000 requests"**
- `0.041 carts/session` → **"4 in 100 sessions add a cart"**
- `5.33e-8 USD/sec` → **"$140/month"**

The denominator is a knob, not a constant. Pick from the audience's
mental model (next section).

### Mode 3 — Magnitude-fit analogy

When neither scaling nor rebasing lands the value. Pair the scaled
number with a tactile reference; don't replace it.

- `$1.4M/day` → "a small house every day"
- `4.3 GW` → "three nuclear reactors' output"
- `12 µs` → "100,000× faster than a blink"
- `67K tokens/$` → "≈ 100 pages of text per dollar"

Use only analogies from the library below. Don't invent.

## Audience-keyed natural denominators

When mode 2 needs a denominator, pick from the audience's list (top is
most preferred):

| Audience | Natural denominators |
|---|---|
| **CFO / business** | customer, conversation, order, session, $1M, day, month |
| **SRE / ops** | request, error, deployment, pod, minute, hour |
| **AI / model** | token, 1M tokens, evaluation, model call, conversation |
| **Customer-facing** | user, page view, session, transaction |
| **Mixed / demo** | start with CFO, fall back to AI, then SRE |

Tie-breaker: if two denominators are equally apt, pick the one that
yields a **bigger numerator**. `3 per 100 customers` reads better than
`0.03 per customer`.

## Analogy library

Curated, additive. Don't invent.

### Spend
- $1 — a coffee
- $10 — a fast-food meal
- $100 — a tank of gas
- $1K — a budget laptop
- $10K — a used car
- $100K — a starter-home down payment
- $1M — a small house
- $10M — a Boeing 737

### Time
- 1 ms — the blink of an eye
- 1 s — a heartbeat
- 1 min — reading a tweet
- 1 hour — a sitcom episode
- 1 day — a full workday

### Bytes
- 1 KB — a paragraph of text
- 1 MB — a photo
- 1 GB — an HD movie
- 1 TB — 250,000 photos
- 1 PB — a film studio's archive

### Tokens
- 100 tokens — a tweet's worth
- 1K tokens — one printed page
- 100K tokens — a short novel
- 1M tokens — ten novels
- 10M tokens — a small library

### Power
- 1 W — an LED bulb
- 1 kW — a microwave at full blast
- 1 MW — a thousand homes
- 1 GW — a nuclear reactor

### AI throughput (tokens per dollar)
- 700 tokens/$ — ≈ 1 page of text per dollar
- 7K tokens/$ — ≈ 10 pages per dollar
- 70K tokens/$ — ≈ 100 pages per dollar
- 700K tokens/$ — ≈ 1,000 pages (a novel) per dollar
- 7M tokens/$ — ≈ 10,000 pages per dollar
- 70M tokens/$ — ≈ a small bookshelf per dollar

## Output contract

Every invocation returns a structured recommendation with these fields:

- **mode** — `scale` / `rebase` / `analogy` / `convention`
- **display_value** — the rendered number
- **unit** — Grafana unit string
- **custom_unit** — Grafana customUnit (leading space)
- **decimals** — int
- **axis_label** — short title fragment
- **description** — plain-English panel tooltip
- **prom_fragment** — the (possibly rebased) PromQL
- **analogy** — tactile phrase, or null
- **notes** — one-line "why this mode"

The user (or downstream dashboard-building skill) applies these fields
directly to the panel JSON.

## Worked example — the canonical case

**Input**:
- metric: `add_to_cart_total`
- typical value: 0.03 per hour
- audience: CFO

**Reasoning**:
- Mode 1: time scale up — `0.72/day` still tiny.
- Mode 2: CFO's preferred denominator is **customer**. Rebase: ATCs ÷ customer_visits × 100. Result lands at "3 per 100 customers". ✅

**Recommendation**:
- mode: `rebase`
- display: `3`, unit: `none`, customUnit: ` per 100 customers`, decimals: `0`
- axis_label: `ATCs per 100 customers`
- description: `Of every 100 customers who visit, this many add something to cart.`
- prom_fragment: `rate(add_to_cart_total[5m]) / rate(customer_visits_total[5m]) * 100`
- notes: `Rebased from /hour to /100 customers — CFO mental model.`

## When NOT to humanize

- The raw value already reads in 1–999 with a recognizable unit (`92%`,
  `1.4 GB`, `340 ms`).
- The dashboard's audience is engineers debugging, who need the raw
  number to correlate with logs/traces.
- The "humanization" would introduce a denominator the audience doesn't
  mentally track (`per session-hour` is not a real mental model).

If in doubt, ask: **"will a CFO understand this in 5 seconds without
explanation?"** If yes, ship. If no, humanize.

## Anti-patterns to refuse

- Inventing an analogy not in the library above.
- Rebasing without naming the denominator (`3 per 100` is meaningless;
  `3 per 100 customers` is a sentence).
- Stacking suffixes (`customers / hour / pod`).
- Picking a denominator the metric doesn't have (if `customer_visits_total`
  isn't being collected, you can't rebase against it).
