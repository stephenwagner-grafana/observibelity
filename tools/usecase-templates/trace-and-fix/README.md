# Archetype: trace-and-fix

## Purpose

Use this archetype when **a single trace ID surfaces the root cause** — one
request produces one structured error span, and the operator's job is to open
the trace, read the error, and apply the canonical fix.

This is the simplest mice-style use case: low-volume, high-clarity. The signal
is the structured error span itself, not aggregate rates. The dashboard panel
exists to let the operator pivot from "I saw the alert" to "I'm reading the
exact span" in one click.

## When to pick this archetype

- The bug is reproducible with a single request payload.
- The error is captured in a structured span attribute (not just an HTTP code).
- The fix is well-defined and one-line-describable.
- The demo flow is: trigger phrase --> backend error --> red span --> dashboard.

If the bug only shows up after N events or only across users, use a different
archetype (cascade, per-user-pattern, or leaderboard).

## Examples from the planner

- `mice-rca` — the canonical "press a button, see a trace, fix the bug" demo.

## Parameters

| name              | purpose                                                          |
| ----------------- | ---------------------------------------------------------------- |
| `name`            | use case slug, used in metric labels and headers                 |
| `app`             | which stub app receives the request (neoncart or supportbot)     |
| `trace_filter`    | the span name pattern that identifies the failing operation      |
| `error_pattern`   | regex matching the error message inside the span                 |
| `dashboard_uid`   | Grafana dashboard UID the alert should link to                   |
| `expected_fix`    | one-line description of the canonical fix (rendered in README)   |
| `trigger_phrase`  | the phrase the loadgen types to provoke the error                |

## Demo flow

1. User types the `trigger_phrase` into the app.
2. The app makes an instrumented call that raises a structured error.
3. The trace appears in Tempo with a red span matching `trace_filter`.
4. The alert fires (severity: medium — informational) and links the operator
   to the dashboard panel filtered by `ai_o11y.usecase={{ name }}`.
5. Operator reads the span, applies `expected_fix`, retests.

## Output artifacts

The compiler emits, per use case using this archetype:

- 1 k6 scenario producing ~1 req/min with the trigger phrase
- 3 Grafana dashboard panels (trace lookup, error rate, top patterns)
- 1 Prometheus alert rule (medium severity)
- 1 Sigil rule evaluator confirming the expected error span exists
