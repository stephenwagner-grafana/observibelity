# Humanize metric values

> **One-sentence purpose.** Convert any `(metric, typical value, audience)` tuple into a display value, unit, decimals, axis label, plain-English description, and PromQL fragment such that a non-expert glances at the panel and instantly understands the scale.

This file is the **single source of truth**. Two surfaces consume it:

1. **Claude skill** `ai-o11y-humanize-metric` (in `.claude/skills/`) — reads this doc, calls `dashboards/humanize.py` for executable lookups, returns a recommendation card.
2. **Grafana Cloud Assistant skill** — paste-body in `HUMANIZE_METRIC.grafana.md` is a self-contained re-flow of this doc for the in-product Assistant.

When this file changes, both wrappers automatically follow. The Python tables (`dashboards/_humanize_table.py`) mirror the tables here; `dashboards/test_humanize.py` enforces parity on a few canonical entries.

---

## 1. The problem

Numbers in observability dashboards routinely fail the **glance test**:

- `0.000003 $/token`
- `0.03 ATCs/hour`
- `1.4e9 bytes/sec`
- `0.041 cart-adds/session`
- `5.33e-8 USD/sec`

An expert reads these instantly. A CFO doesn't. The job of this skill is to choose a representation that lands in **1–999** with a denominator the audience already cares about — and, when neither lands, to attach a tactile **analogy** so the magnitude feels real.

The existing `_design_tokens.py` `UNIT` dict, `dashboard_lint.py check_unit_rules`, and the `human_readable_units.md` memory cover the **80%** case (per-hour cost, per-minute calls, etc.). This skill covers the **other 20%** — when the standard convention still produces an unreadable number, and a human expert would re-frame the metric entirely.

---

## 2. The three humanization modes

Try them **in order**. The first one that produces:

- a numerator in **1–999** (ideally 1–100), **and**
- a denominator from the audience's mental model,

…wins. If none works, fall through to mode 3 (analogy).

### Mode 1 — Unit-family / SI scaling

When the metric's unit family has standard prefixes or conversions and applying one lands in 1–999.

| Raw | Humanized | Move |
|---|---|---|
| `1500 ms` | `1.5 s` | s prefix up |
| `0.041 s` | `41 ms` | s prefix down |
| `1.2e9 bytes` | `1.2 GB` | bytes → GB |
| `1500000 tokens` | `1.5M tokens` | short suffix |
| `4300 W` | `4.3 kW` | W → kW |
| `0.000012 °C` | (not useful) | temperature doesn't scale this way |

This is mechanical. The existing `_design_tokens.py UNIT` already covers most of this. **If mode 1 works, stop here.**

### Mode 2 — Denominator rebasing

When the metric is a **rate or ratio with a tiny numerator** and there's a natural alternative denominator in the audience's mental model.

The move: replace `X per second` (which is unreadable) with `Y per <thing the audience cares about>`.

| Raw | Rebased | Mental model |
|---|---|---|
| `0.03 ATCs/hour` (max) | **"3 ATCs per 100 customers"** | CFO thinks in customers, not hours |
| `0.000003 $/token` | **"$3 per 1M tokens"** | nobody thinks in single tokens |
| `0.0001 errors/sec` | **"1 error per 10,000 requests"** | SRE thinks in request volume |
| `0.041 carts/session` | **"4 in 100 sessions add a cart"** | conversion ratio, not raw rate |
| `5.33e-8 USD/sec` | **"$0.19/hour"** or **"$140/month"** | time rebase up |
| `0.00343 calls/sec/user` | **"1 call every 5 minutes per user"** | inverted + rebased |

**Key insight**: the denominator is a knob, not a constant. Time isn't sacred — you can rebase against population, volume, value, or unit count. The denominator must be **a quantity the audience already mentally tracks**.

This is the move that does the heavy lifting and that mechanical unit tokens cannot do.

### Mode 3 — Magnitude-fit analogy

When neither scaling nor rebasing lands the value somewhere intuitive — usually for **very large** or **very small** headline numbers where the magnitude itself is the story.

Pair with the scaled number; don't replace it. The number stays for engineers; the analogy lands for execs.

| Scaled | Analogy | Domain |
|---|---|---|
| `$1.4M/day` | "a small house every day" | spend |
| `$905K/hour` | "a Tesla every minute" | spend |
| `4.3 GW` | "three nuclear reactors' output" | power |
| `12 µs` | "100,000× faster than a blink" | latency |
| `3.2 ng` | "1/30,000 of a grain of rice" | mass |
| `92% capture` | "9 out of 10 carts succeed" | conversion |
| `67K tokens/$` | "≈ 100 pages of text per dollar" | AI throughput |

Analogies are pulled from the **`ANALOGIES`** table (next section). Don't invent on the fly — invented analogies skew, drift, or land badly. Add to the table, then use.

---

## 3. Audience-keyed natural denominators

When mode 2 needs a denominator, pick from the audience's preferred list (top is most preferred).

| Audience | Natural denominators (most → least preferred) |
|---|---|
| **CFO / business** | customer, conversation, order, session, $1M, day, month |
| **SRE / ops** | request, error, deployment, pod, minute, hour |
| **AI / model** | token, 1M tokens, evaluation, model call, conversation |
| **Customer-facing** | user, page view, session, transaction |
| **Mixed / demo** | first try CFO list, then AI list, then SRE — heroes lean business |

**Disambiguation rule**: if two denominators tie on preference (e.g. "per session" vs. "per customer"), pick the one with the **larger denominator value**, because it leaves a bigger numerator. `3 per 100 customers` reads better than `0.03 per customer`.

---

## 4. Analogy library

Curated, additive, versioned. New entries land via PR with at least one citation/source.

| Magnitude | Domain | Analogy | Useful for |
|---|---|---|---|
| `$1` | spend | a coffee | tiny per-call cost |
| `$10` | spend | a fast-food meal | per-conversation cost |
| `$100` | spend | a tank of gas | per-hour cost in dev |
| `$1K` | spend | a budget laptop | per-day cost |
| `$10K` | spend | a used car | per-week LLM bill |
| `$100K` | spend | a starter home down-payment | per-month enterprise |
| `$1M` | spend | a small house | per-day outage cost |
| `$10M` | spend | a Boeing 737 | quarterly mega-spend |
| `1 ms` | time | the blink of an eye | UI responsiveness |
| `1 s` | time | a heartbeat | API latency |
| `1 min` | time | reading a tweet | batch process |
| `1 hour` | time | a sitcom episode | session length |
| `1 day` | time | the workday | data retention |
| `1 KB` | bytes | a paragraph | text payload |
| `1 MB` | bytes | a photo | small video |
| `1 GB` | bytes | an HD movie | logs/hour |
| `1 TB` | bytes | 250K photos | cluster storage |
| `1 token` | AI | ¾ of a word, ≈ 4 chars | one unit of LLM text |
| `100 tokens` | AI | a tweet | one short reply |
| `1K tokens` | AI | one printed page | one long reply |
| `100K tokens` | AI | a short novel | one full conversation |
| `1M tokens` | AI | ten novels | one billing cycle |
| `1 W` | power | an LED bulb | idle pod |
| `1 kW` | power | a microwave at full blast | small server |
| `1 MW` | power | 1000 homes' draw | data hall |
| `1 GW` | power | a nuclear reactor | hyperscale region |

**Domain combos that show up in AI o11y** (each one is a tested phrasing):

- `tokens/$` → "**N pages of text per dollar**" (1 page ≈ 700 output tokens)
- `$/conversation` → "**a coffee per conversation**" at ~$3
- `tokens/sec/GPU` → "**N words/sec per GPU**" (1 token ≈ 0.75 words)
- `requests/pod/sec` → "**N per heartbeat**" at ~1/sec

---

## 5. Decision tree

```
START
  │
  ├─ Is the raw value in 1–999 with a recognizable unit? ──── YES → STOP. No humanization needed.
  │           │
  │           NO
  │           │
  ├─ Mode 1: Can SI / unit-family scaling land it in 1–999?  ── YES → Apply scaling. STOP.
  │           │
  │           NO (still tiny rate, or no SI prefix available)
  │           │
  ├─ Mode 2: Is there a natural denominator in the
  │           audience's list that lands the numerator in 1–999? ── YES → Rebase. Document the denominator
  │           │                                                            in the panel description.
  │           NO
  │           │
  ├─ Mode 3: Is the magnitude itself the story
  │           (very large $/event, very small µs/event)?         ── YES → Scale to nearest SI, ATTACH analogy
  │           │                                                            from table § 4.
  │           NO
  │           │
  └─ Punt: use the convention default (`UNIT` dict in `_design_tokens.py`) and flag with TODO.
```

---

## 6. Output contract

Every call to this skill (Claude or Grafana) returns a structured **Recommendation** with these fields:

| Field | Type | Example (ATC case) |
|---|---|---|
| `mode` | `"scale"` / `"rebase"` / `"analogy"` / `"convention"` | `"rebase"` |
| `display_value` | string | `"3"` |
| `unit` | Grafana unit string | `"none"` |
| `custom_unit` | string (leading space) | `" per 100 customers"` |
| `decimals` | int | `0` |
| `axis_label` | string | `"ATCs per 100 customers"` |
| `description` | string (panel description tooltip) | `"Of every 100 customers who visit, this many add something to cart."` |
| `prom_fragment` | string (the rebased PromQL) | `"rate(add_to_cart_total[5m]) / rate(customer_visits_total[5m]) * 100"` |
| `analogy` | string or null | `null` |
| `notes` | string | `"Rebased from /hour to /100 customers because CFO mental model is customers."` |

The Grafana-builder skill consumes this struct and emits the panel JSON. The dashboard-critic consults the same struct to score the "Human-scaled numbers" axis objectively.

---

## 7. Worked examples

### Example A — ATC rate (the canonical case)

**Input**:
- `metric_name = "add_to_cart_total"`
- `typical_value = 0.03` (per hour, max)
- `audience = "CFO"`
- `available_denominators = ["customer_visits_total"]`

**Reasoning**:
- Mode 1: time scale up — `0.72/day` still tiny.
- Mode 2: CFO's preferred denominator is **customer**, and `customer_visits_total` is available. Rebase: `ATC / customer_visits * 100` → `3 per 100 customers`. ✅

**Recommendation**:
- mode = `rebase`
- display = `3`, unit = `none`, custom_unit = `" per 100 customers"`, decimals = `0`
- axis_label = `ATCs per 100 customers`
- description = `Of every 100 customers who visit, this many add something to cart.`
- prom_fragment = `rate(add_to_cart_total[5m]) / rate(customer_visits_total[5m]) * 100`
- notes = `Rebased from /hour to /100 customers — CFO mental model.`

### Example B — Best value model per token/USD (from the screenshot)

**Input**:
- `metric_name = "gen_ai_client_token_usage_total{token_type='output'} / gen_ai_client_cost_USD_total"`
- `typical_value` ranges from ~50K (paid Sonnet) to ~50M (local Ollama)
- `audience = "Mixed"`

**Reasoning**:
- Mode 1: short suffix lands it (`67K` to `50M` tokens/$). Works, but the *unit* "tokens per dollar" is opaque to a non-AI audience.
- Mode 3: attach analogy. 1 page ≈ 700 output tokens, so divide by 700 → pages per dollar. `67K/$ → 100 pages/$`, `50M/$ → 70K pages/$`. ✅

**Recommendation**:
- mode = `analogy`
- display = `67K` (scaled), unit = `short`, custom_unit = `" tokens / $"`, decimals = `0`
- axis_label = `Tokens per dollar`
- description = `How much text you get per dollar — at ~700 tokens/page, Sonnet ≈ 100 pages/$, Haiku ≈ 700, local Ollama ≈ 70K+.`
- analogy = `≈ 100 pages of text per dollar` (specific to ~67K)
- notes = `Scaled (mode 1) for engineers; analogy attached (mode 3) for non-AI viewers.`

### Example C — Spend rate

**Input**:
- `metric_name = "gen_ai_client_cost_USD_total"`
- `typical_value = 5.33e-8` (per-second rate)
- `audience = "CFO"`

**Reasoning**:
- Mode 1: not applicable (no SI prefix for $).
- Mode 2: CFO list — `day` available; rebase `* 86400` → `$0.0046/day` still tiny. Try `month` → `$0.14/month`. ✅ Lands in 1–999.

**Recommendation**:
- mode = `rebase`
- display = `0.14`, unit = `currencyUSD`, custom_unit = `" /month"`, decimals = `2`
- axis_label = `Spend per month (projected)`
- description = `If the current rate held for a full month, the bill would be this much.`
- prom_fragment = `rate(gen_ai_client_cost_USD_total[5m]) * 2592000`
- notes = `Per-second too small for /hour or /day; projected to monthly run-rate.`

### Example D — Error rate

**Input**:
- `metric_name = "http_5xx_total"`
- `typical_value = 0.0001` per second
- `audience = "SRE"`

**Reasoning**:
- Mode 1: time scale — `0.36/hour` or `8.6/day` (works, but loses the "vs. successful requests" framing).
- Mode 2: SRE list — **request** available. Rebase `errors / requests * 10000` → `1 per 10,000 requests`. ✅

**Recommendation**:
- mode = `rebase`
- display = `1`, unit = `none`, custom_unit = `" per 10K requests"`, decimals = `1`
- axis_label = `Errors per 10K requests`
- description = `How many requests fail out of every ten thousand.`
- prom_fragment = `rate(http_5xx_total[5m]) / rate(http_requests_total[5m]) * 10000`

---

## 8. When NOT to humanize

- The raw value already reads in 1–999 with a recognizable unit (`92%`, `1.4 GB`, `340 ms`) — **don't over-engineer.**
- The dashboard's audience is **engineers debugging**, and they need the raw number to correlate with logs/traces.
- The metric is internal / not surfaced on a panel.
- The "humanization" would introduce a denominator the audience doesn't actually track (`per session-hour` is not a real mental model).

If in doubt, ask: **"will a CFO understand this in 5 seconds without explanation?"** If yes, ship. If no, humanize.

---

## 9. Anti-patterns

- **Inventing an analogy on the fly.** Skews and drifts. Add to § 4 first, then use.
- **Rebasing without naming the denominator.** `3 per 100` is meaningless; `3 per 100 customers` is a sentence. The denominator goes in `custom_unit` AND in the description.
- **Stacking three custom suffixes.** `" customers / hour / pod"` fails the glance test by definition. Pick one denominator.
- **Hiding the raw query.** Always show the rebased PromQL in `prom_fragment` so reviewers can audit.
- **Picking a denominator the metric doesn't have.** If `customer_visits_total` doesn't exist as a series, you can't rebase against it. Fall through to mode 1 or 3, don't fabricate.

---

## 10. How to extend

| Change | What to update |
|---|---|
| New analogy entry | § 4 table here **+** `_humanize_table.py ANALOGIES` **+** a test in `test_humanize.py` |
| New audience profile | § 3 table here **+** `_humanize_table.py AUDIENCE_DENOMINATORS` |
| New unit family with SI ladder | `_humanize_table.py UNIT_FAMILIES` only (mode 1 is mechanical, no doc update needed unless the family is exotic) |
| New worked example | § 7 here only (examples are illustrative, not consumed programmatically) |

Every change goes through PR, lands in both surfaces by re-pasting the Grafana body and re-running the lint suite.

---

## 11. Pipeline integration

This skill sits **between** `ai-o11y-story-architect` (which picks the hero metric) and `ai-o11y-grafana-builder` (which writes the JSON).

```
story-architect          humanize-metric           grafana-builder
   │                          │                         │
   │  hero metric chosen      │                         │
   ├─────────────────────────►│                         │
   │  (name, typical, aud.)   │                         │
   │                          │  Recommendation         │
   │                          ├────────────────────────►│
   │                          │  (unit, decimals,       │
   │                          │   prom_fragment,        │
   │                          │   description, …)       │
```

`ai-o11y-dashboard-critic` also calls `humanize()` on each panel during scoring, comparing the recommendation to what's actually in the JSON — divergence is the objective signal for the "Human-scaled numbers" axis.

`dashboard_lint.py` adds a soft check: `unit.humanize-diverges` (WARN) when the panel's unit/decimals/customUnit doesn't match the recommendation. Soft because some divergence is intentional (engineer-targeted panels).
