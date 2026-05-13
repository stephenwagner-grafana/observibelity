# Archetype: cascade

## Purpose

Use this archetype when **a counter exceeds N per session/minute** -
email cascades, token spikes, tool-call runaways. The signal is one
conversation accumulating an unreasonable count of a thing.

This is the "the agent got stuck in a loop and sent 47 emails" archetype.

## When to pick this archetype

- A counter (emails sent, tokens spent, tool calls made) accumulates
  inside a single session or in a short window.
- The signal is best expressed as `counter > threshold per window`.
- A sticky persona / session is the "victim" demonstrating the cascade.
- Severity is `critical` - cascades cause real damage (cost, spam,
  external side-effects).

If the counter accumulates over many users (e.g. global rate spike),
that's leaderboard with `group_by=app`. If you want zero tolerance on
one event, use single-event-severity.

## Examples from the planner

- `email_cascade` — agent sends N+ emails in one session.
- `token_spikes` — token consumption spikes N+ per session/minute.
- `tool_call_runaway` — agent calls tools N+ times in one conversation.

## Parameters

| name                 | purpose                                                   |
| -------------------- | --------------------------------------------------------- |
| `name`               | use case slug                                             |
| `app`                | which stub app receives the request                       |
| `counter_metric`     | the prometheus counter being watched                      |
| `threshold`          | the value the counter must exceed                         |
| `window`             | the window over which the counter accumulates             |
| `cascade_persona`    | the sticky persona running the cascade arc                |
| `cascade_messages`   | JSON list of messages in the cascade conversation         |
| `cascade_interval`   | seconds between messages in the cascade                   |

## Demo flow

1. Loadgen runs the cascade arc once per N minutes: persona
   `u-{{ cascade_persona }}` sends each message in `cascade_messages`
   back-to-back, accumulating the counter inside one session.
2. The "per-session tool-call count" panel shows the offending
   session's bar growing in real time.
3. When the counter crosses `threshold` within `window`, the alert
   fires at severity=critical.
4. The "cumulative damage gauge" makes the operational impact
   (cost, emails sent, etc.) obvious.

## Output artifacts

- 1 k6 scenario running the cascade arc per the sticky persona
- 4 Grafana panels (per-session count, cascade timeline, top
  offending sessions, cumulative damage gauge)
- 1 Prometheus alert rule (counter > threshold per window)
- 1 Sigil rule evaluator counting cascade events per conversation
