// k6 scenario template: trace-and-fix archetype
// Generated for use case: {{ name }}
// App target:           {{ app }}
// Trace filter:         {{ trace_filter }}
// Trigger phrase:        {{ trigger_phrase }}
//
// Rate: ~1 request per minute. Goal is one trace per minute that produces
// the structured error span identified by `trace_filter`. The compiler
// substitutes Jinja variables and writes the final scenario to
// loadgen/scenarios/{{ name }}.js.

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    '{{ name }}_trace_and_fix': {
      executor: 'constant-arrival-rate',
      rate: 6,
      timeUnit: '1m',
      duration: '60s',
      preAllocatedVUs: 1,
      maxVUs: 2,
      exec: 'fire',
    },
  },
  thresholds: {
    // We expect the error - don't fail the scenario on 5xx.
    http_req_failed: ['rate<1.0'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://{{ app }}.observibelity.svc.cluster.local';

export function fire() {
  const payload = JSON.stringify({
    message: '{{ trigger_phrase }}',
    persona_id: 'trace.fix.{{ name }}',
    usecase: '{{ name }}',
    session_id: `s-${Date.now()}`,
    metadata: {
      usecase: '{{ name }}',
      archetype: 'trace-and-fix',
    },
  });

  const headers = {
    'Content-Type': 'application/json',
    'ai_o11y-usecase': '{{ name }}',
    'ai_o11y-archetype': 'trace-and-fix',
    'ai_o11y-trace-filter': '{{ trace_filter }}',
    'X-Trigger-Phrase': '{{ trigger_phrase }}',
  };

  const res = http.post(`${BASE_URL}/chat`, payload, { headers });

  check(res, {
    'trace span emitted': (r) => r.headers['X-Trace-Id'] !== undefined,
  });

  sleep(1);
}
