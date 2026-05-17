---
name: ai-o11y-humanize-metric
description: Convert a metric's raw value into a panel-ready humanized representation — display value, unit, decimals, axis label, plain-English description, and rebased PromQL. Use when a panel value fails the glance test (sci-notation, sub-1 rates, opaque per-token costs), when choosing the hero metric in story-architect, when the dashboard-critic flags "Human-scaled numbers", or when the user says "what's the right unit for…" / "this number reads weird" / "humanize this". Three modes: SI scaling, denominator rebasing, magnitude-fit analogy. Advisory — never writes JSON.
allowed-tools: Read, Bash, Grep
---

# ai-o11y-humanize-metric

The unit-and-magnitude advisor for every dashboard panel. Sits between
`ai-o11y-story-architect` (which picks the hero) and
`ai-o11y-grafana-builder` (which writes the JSON), and is consulted by
`ai-o11y-dashboard-critic` to score the "Human-scaled numbers" axis.

The canonical spec is **`dashboards/skills/HUMANIZE_METRIC.md`**. Read
that first; this file is the Claude-side procedure.

## When to trigger

When the user says ANY of:
- "What's the right unit for X?"
- "This number reads weird / lands wrong / fails the glance test"
- "Humanize this metric / panel / value"
- "How would a CFO read this?"
- "Why is this $0.000003?" / "Why is this 0.03 per hour?"

OR when **any** of these conditions hold inside another skill's flow:
- `ai-o11y-story-architect` is about to commit a hero metric whose typical
  value is outside 1–999, **or** whose unit family is opaque to the
  declared audience.
- `ai-o11y-grafana-builder` is about to emit a panel `unit` / `decimals`
  for a metric whose typical value lands as scientific notation, leading
  zeros, or a sub-1 rate.
- `ai-o11y-dashboard-critic` finds a stat where `display_value` is
  exponential, `0.00`, or has more than 4 decimals.

## What this skill does NOT do

- **Does not write JSON.** Returns a recommendation; `ai-o11y-grafana-builder`
  applies it.
- **Does not invent analogies.** The analogy library lives in
  `dashboards/_humanize_table.py ANALOGIES`. Add an entry first, then use.
- **Does not pick the metric.** Story-architect's job.
- **Does not score.** Critic's job — though it consumes this skill's output.

## Procedure

### 1. Read the spec

```bash
cat dashboards/skills/HUMANIZE_METRIC.md
```

Specifically:
- §2 (three modes) for the decision logic
- §3 (audience denominators) for who-thinks-in-what
- §4 (analogy library) for available tactile references
- §7 (worked examples) for paste-able patterns

### 2. Collect the inputs

You need **at minimum**:

| Input | Source | Example |
|---|---|---|
| `metric_name` | the panel's metric or expression | `add_to_cart_total` |
| `typical_value` | what it reads at steady-state (per-second for rates) | `0.03 / 3600 = 8.3e-6` |
| `audience` | from `dashboards/skills/NARRATIVE.md` or story plan | `"CFO"` |

Strongly preferred:
- `unit_family` (one of `time`, `bytes`, `currency_usd`, `power`, `count`, `tokens`, `ratio`)
- `is_rate` (true if Prom rate / per-second)
- `domain` (for mode 3 analogy: `spend`, `time`, `bytes`, `tokens`, `power`, `ai_throughput`)
- `available_series` — list of Prom metric names that could serve as denominators

To find available series for a rebase candidate:

```bash
# Verify a candidate denominator metric actually exists
gcx metrics names --filter 'customer_visits_total|nc_session_total' 2>&1 || true
```

### 3. Call `humanize()`

Two ways:

**A. Python REPL (preferred for one-off panels):**

```bash
cd dashboards && python3 -c '
import sys; sys.path.insert(0, ".")
from humanize import humanize
import json
rec = humanize(
    "add_to_cart_total",
    0.03 / 3600,
    audience="CFO",
    is_rate=True,
    available_series=("customer_visits_total",),
)
print(json.dumps(rec.as_dict(), indent=2))
'
```

**B. CLI shorthand (for grep-able output):**

```bash
cd dashboards && python3 humanize.py add_to_cart_total $(python3 -c 'print(0.03/3600)') \
    --audience CFO --rate --series customer_visits_total
```

### 4. Sanity-check the recommendation

Before handing off, ask:
- Does `display_value` land in 1–999? If not, the picker had nothing to anchor on — escalate (try a different denominator, try mode 3 with an explicit `domain`).
- Does `custom_unit` name the denominator? (`per 100 customers` ✅, `per 100` ❌)
- Does `prom_fragment` reference real series? (Run a 1-line `gcx metrics query` to verify.)
- Would a CFO understand this in 5 seconds without explanation?

### 5. Output the recommendation

Format as a markdown card for the human, plus a structured block the
downstream skill can paste:

```markdown
# Humanize: <metric_name>

**Mode**: <scale | rebase | analogy | convention>

| Field | Value |
|---|---|
| display | <value> |
| unit | <grafana unit> |
| customUnit | <suffix> |
| decimals | <n> |
| axisLabel | <label> |
| description | <plain English> |
| analogy | <phrase or —> |

**PromQL fragment** (paste into the panel target):
```promql
<prom_fragment>
```

**Why this mode**: <one sentence from `notes`>

**Open question** (optional): <if the recommendation is uncertain, name the trade-off>
```

### 6. Hand off

- If invoked from `ai-o11y-story-architect`: return to the architect, who
  bakes the hero metric line.
- If invoked from `ai-o11y-grafana-builder`: pass the structured fields
  back; builder applies them to the panel JSON.
- If invoked from `ai-o11y-dashboard-critic`: builder is the route for any
  divergence the critic flags.

## Anti-patterns to refuse

- **Inventing an analogy.** If `pick_analogy(domain, value)` returns
  `None`, do not make one up. Either add an entry to `ANALOGIES` (with a
  test) and re-run, or skip the analogy.
- **Rebasing without a real denominator.** `per 100 customers` requires
  `customer_visits_total` (or equivalent) to actually exist in Prom. If
  it doesn't, fall through to mode 1 or 3.
- **Stacking suffixes.** `customers / hour / pod` is illegible. Pick one
  denominator.
- **Touching the panel JSON.** This skill is advisory. Hand the
  recommendation to `ai-o11y-grafana-builder`; do not edit `dashboards/<uid>.json`.
- **Skipping the spec.** Re-read `HUMANIZE_METRIC.md` if the case is
  ambiguous; the worked examples in §7 cover most ATC-flavored cases.

## When to extend the data tables

| Change | Update |
|---|---|
| New analogy phrase | `_humanize_table.py ANALOGIES` + `test_humanize.py` golden + § 4 in spec |
| New audience profile | `_humanize_table.py AUDIENCE_DENOMINATORS` + § 3 in spec |
| New unit family | `_humanize_table.py UNIT_FAMILIES` only |

Always commit data + test + spec in one PR. The Grafana paste-body
(`dashboards/skills/HUMANIZE_METRIC.grafana.md`) is regenerated from the
spec — bump it in the same commit so the two surfaces stay in lockstep.

## Files this skill touches

| File | Read | Write |
|---|---|---|
| `dashboards/skills/HUMANIZE_METRIC.md` | ✅ (spec) | — |
| `dashboards/_humanize_table.py` | ✅ (via import) | only on `extend` |
| `dashboards/humanize.py` | ✅ (via call) | rarely |
| `dashboards/test_humanize.py` | — | only on `extend` |
| `dashboards/<uid>.json` | — | ❌ never (advisory) |
