// k6 scenario template: single-event-severity archetype
// Generated for use case: {{ name }}
// App target:           {{ app }}
// Event pattern:        {{ event_pattern }}
// Severity signal:      {{ severity_signal }}
//
// Three streams:
//  - critical: ~{{ critical_rate_per_hour }}/hr - should fire the alert
//  - near_miss: ~{{ near_miss_rate_per_hour }}/hr - visible, no alert
//  - innocent: filler so the dashboard timeline has shape

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    '{{ name }}_critical': {
      executor: 'constant-arrival-rate',
      rate: {{ critical_rate_per_hour }},
      timeUnit: '1h',
      duration: '60s',
      preAllocatedVUs: 1,
      maxVUs: 2,
      exec: 'fireCritical',
    },
    '{{ name }}_near_miss': {
      executor: 'constant-arrival-rate',
      rate: {{ near_miss_rate_per_hour }},
      timeUnit: '1h',
      duration: '60s',
      preAllocatedVUs: 1,
      maxVUs: 2,
      exec: 'fireNearMiss',
    },
    '{{ name }}_innocent': {
      executor: 'constant-arrival-rate',
      rate: 6,
      timeUnit: '1m',
      duration: '60s',
      preAllocatedVUs: 2,
      maxVUs: 4,
      exec: 'fireInnocent',
    },
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://{{ app }}.observibelity.svc.cluster.local';
const INNOCENT_MESSAGES = [
  'how do I reset my password',
  'what is your support hours',
  'where do I find my order history',
];

function post(message, severity, kind) {
  const payload = JSON.stringify({
    message: message,
    persona_id: `u-{{ name }}-${Math.floor(Math.random() * 100)}`,
    session_id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    metadata: {
      usecase: '{{ name }}',
      archetype: 'single-event-severity',
      severity: severity,
      kind: kind,
    },
  });
  const headers = {
    'Content-Type': 'application/json',
    'ai_o11y-usecase': '{{ name }}',
    'ai_o11y-archetype': 'single-event-severity',
    'ai_o11y-severity': severity,
    'ai_o11y-kind': kind,
  };
  const res = http.post(`${BASE_URL}/chat`, payload, { headers });
  check(res, { 'request accepted': (r) => r.status < 500 });
  sleep(1);
}

export function fireCritical() {
  post('TRIGGER_CRITICAL: {{ event_pattern }}', 'critical', 'critical');
}

export function fireNearMiss() {
  post('TRIGGER_NEAR_MISS: looks like {{ event_pattern }} but is benign', 'low', 'near_miss');
}

export function fireInnocent() {
  const msg = INNOCENT_MESSAGES[Math.floor(Math.random() * INNOCENT_MESSAGES.length)];
  post(msg, 'info', 'innocent');
}
