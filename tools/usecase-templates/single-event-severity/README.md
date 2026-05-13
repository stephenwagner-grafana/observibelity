# Archetype: single-event-severity

## Purpose

Use this archetype when **any single critical event must fire an alert** -
PII leakage, hiring-discrimination, prompt-injection success. Zero
tolerance. The operator's job is to read the offending event and the
trace, then triage immediately.

This is the "we don't accumulate, we page on first hit" archetype.

## When to pick this archetype

- The cost of one event slipping through is unacceptable.
- The event is rare; aggregate rates are not useful.
- Near-miss cases should still be visible on the dashboard but should
  NOT page.
- Severity is `critical`. Alert fires on the FIRST event in 5m.

If you want a leaderboard or rate trend, use leaderboard. If a counter
needs to cross N, use cascade. If pattern repetition by one persona is
the signal, use per-user-pattern.

## Examples from the planner

- `pii_echo` — the assistant echoed a credit card / SSN / address back.
- `hiring_discrimination_risk` — output suggested a protected-class
  hiring filter.
- `prompt_injection` — a prompt-injection payload changed model
  behavior in a measurable way.

## Parameters

| name              | purpose                                                            |
| ----------------- | ------------------------------------------------------------------ |
| `name`            | use case slug                                                      |
| `app`             | which stub app receives the request                                |
| `event_pattern`   | regex/expression identifying the critical event                    |
| `severity_signal` | how the critical severity is marked on the event                   |
| `near_miss_pattern` | (optional) regex for near-miss cases - visible but no alert      |
| `critical_rate_per_hour` | how often the loadgen produces the critical event           |
| `near_miss_rate_per_hour` | how often the loadgen produces the near-miss event         |

## Demo flow

1. Loadgen produces mostly innocent traffic plus rare near-miss events
   and ultra-rare critical events (~3-5/hr).
2. When the first critical event fires, the alert pages immediately.
3. The dashboard's "last 10 critical events" panel includes a trace
   link so the operator can drill in in one click.
4. The severity histogram shows the near-misses surrounding the
   critical, giving context.

## Output artifacts

- 1 k6 scenario at ~3-5 critical/hr plus a near-miss baseline
- 3 Grafana panels (per-event timeline, severity histogram, last 10
  critical events table)
- 1 Prometheus alert rule (severity=critical, fires on first event)
- 1 Sigil rule evaluator marking severity=critical on event_pattern
