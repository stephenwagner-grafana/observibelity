# Archetype: leaderboard

## Purpose

Use this archetype when **a rate or count is ranked across a category** -
model performance, brand-voice scores, refund-compliance rates,
hallucination rates. The operator's job is to read the leaderboard, spot
the outlier, and either reward the winner or investigate the regression.

This is the "which model is winning right now?" archetype: aggregate signal,
ranked dimension, regression detection over time.

## When to pick this archetype

- The signal is best expressed as `topk(N, sum by (dimension) (metric))`.
- The dimension has multiple stable values (model names, brand styles,
  agents, query types).
- You care about regression vs baseline, not zero-tolerance events.
- A trend line over 24h tells a story.

If the leaderboard is over `persona_id`, that's per-user-pattern, not this.
If a single event matters, use single-event-severity.

## Examples from the planner

- `model_winner` — which LLM is winning on quality across categories?
- `quality_trend` — quality score trending up/down per dimension over 24h.
- `brand_voice_drift` — brand-voice score regressing per agent.
- `hallucination_rate` — hallucination counts ranked per model.
- `refund_compliance` — refund-compliance rate ranked per agent.

## Parameters

| name                   | purpose                                                       |
| ---------------------- | ------------------------------------------------------------- |
| `name`                 | use case slug                                                 |
| `app`                  | which stub app receives the request                           |
| `rank_by`              | the metric / promql expression the leaderboard ranks          |
| `group_by`             | the dimension (model, brand_voice, agent_id, ...)             |
| `categories`           | JSON list of category values to seed in the baseline traffic  |
| `baseline_rate`        | requests per minute across all categories                     |
| `regression_threshold` | fraction (e.g. 0.15 = 15%) below baseline to alert            |
| `baseline_window`      | window over which baseline is computed (e.g. 24h)             |

## Demo flow

1. Loadgen produces baseline traffic across every category so each one has
   signal.
2. The leaderboard panel ranks the top 10 categories by `rank_by` grouped
   by `group_by`.
3. The trend line shows movement over 24h - operators see a category
   slipping before it crosses the alert.
4. The regression detector compares the current window to baseline and
   fires when any category drops by `regression_threshold`.

## Output artifacts

- 1 k6 scenario producing baseline traffic across all categories
- 3 Grafana panels (leaderboard bar, trend timeseries, regression detector)
- 1 Prometheus alert rule (regression vs baseline)
- 1 Sigil rubric evaluator producing the leaderboard signal
