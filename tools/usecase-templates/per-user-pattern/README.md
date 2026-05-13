# Archetype: per-user-pattern

## Purpose

Use this archetype when **an offender persona repeats a pattern**, and the
operator's job is to spot that persona on a leaderboard before they cause
real damage. The signal is not the individual event - it's the *repetition*
by a sticky `persona_id` exceeding a baseline of innocent users.

This is the "Tim from accounting keeps trying to exfil data" archetype: one
event is suspicious, three events is a pattern, and the leaderboard makes
the offender obvious.

## When to pick this archetype

- A sticky `persona_id` repeats the same pattern across N requests.
- The leaderboard `topk(N, sum by (persona_id) ...)` cleanly separates the
  offender from baseline traffic.
- The signal is the *rate per persona*, not aggregate volume.
- The alert fires on per-persona breach (typically: >=3 hits in 15m AND
  >20% of messages flagged).

If any single event should fire (zero tolerance), use single-event-severity.
If a counter accumulates inside one conversation, use cascade.

## Examples from the planner

- `tim_exfil` — same engineer keeps asking for payroll dumps.
- `mara_cowork_term` — terminated employee patterns surface in queries.
- `jordan_disclosure` — disclosure-pattern messages from one persona.
- `priya_cost` — same user consistently runs the most expensive flows.

## Parameters

| name                   | purpose                                                       |
| ---------------------- | ------------------------------------------------------------- |
| `name`                 | use case slug, used in metric labels and headers              |
| `app`                  | which stub app receives the request (neoncart or supportbot)  |
| `persona_id`           | the sticky user ID (e.g. `tim-engineering-42`)                |
| `pattern_signature`    | substring/regex identifying the pattern in payload            |
| `message_template`     | the prompt the persona keeps sending (Jinja string)           |
| `message_count`        | how many messages the persona sends per scenario run          |
| `weight`               | multiplier over baseline persona rate                         |
| `score_calculation`    | promql snippet that scores per-persona hits                   |
| `leaderboard_metric`   | counter that the topk leaderboard ranks                       |
| `alert_threshold`      | how many hits in 15m before the per-persona alert fires       |

## Demo flow

1. Loadgen spins up the sticky persona (`persona_id`) and a baseline pool.
2. The sticky persona sends `message_count` requests, each matching
   `pattern_signature`. Baseline personas send unrelated messages.
3. The leaderboard panel ranks personas by `leaderboard_metric` - the
   sticky persona rockets to the top.
4. The alert fires when the persona breaches `alert_threshold`.
5. Operator drills down (persona variable), reads the per-user timeline,
   sees every offending message in one place.

## Output artifacts

- 1 k6 scenario with `weight x baseline` rate for the sticky persona
- 4 Grafana panels (leaderboard, timeseries, drilldown, alert state)
- 1 Prometheus alert rule (per-persona threshold)
- 2 Sigil evaluators (rule + rubric)
