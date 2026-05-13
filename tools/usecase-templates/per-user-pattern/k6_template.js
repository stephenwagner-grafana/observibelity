// k6 scenario template: per-user-pattern archetype
// Generated for use case: {{ name }}
// App target:           {{ app }}
// Persona:              {{ persona_id }}
// Pattern signature:    {{ pattern_signature }}
//
// Sticky persona u-{{ persona_id }} sends {{ message_count }} messages,
// each matching the pattern signature. Rate is {{ weight }}x baseline
// so the persona surfaces on the leaderboard.

import http from 'k6/http';
import { check, sleep } from 'k6/check';

export const options = {
  scenarios: {
    {{ name }}_offender: {
      executor: 'constant-arrival-rate',
      rate: {{ weight }},
      timeUnit: '1m',
      duration: '24h',
      preAllocatedVUs: 2,
      maxVUs: 4,
      exec: 'fireOffender',
    },
    {{ name }}_baseline: {
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: '1m',
      duration: '24h',
      preAllocatedVUs: 4,
      maxVUs: 8,
      exec: 'fireBaseline',
    },
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://{{ app }}.observibelity.svc.cluster.local';
const PATTERN_MESSAGES = [
  '{{ message_template }}',
];
const BASELINE_PERSONAS = ['u-base-a', 'u-base-b', 'u-base-c', 'u-base-d'];

export function fireOffender() {
  const msg = PATTERN_MESSAGES[Math.floor(Math.random() * PATTERN_MESSAGES.length)];
  const payload = JSON.stringify({
    message: msg,
    user_id: '{{ persona_id }}',
    session_id: `s-{{ persona_id }}-${Date.now()}`,
    metadata: {
      usecase: '{{ name }}',
      archetype: 'per-user-pattern',
      pattern_signature: '{{ pattern_signature }}',
    },
  });
  const headers = {
    'Content-Type': 'application/json',
    'ai_o11y-usecase': '{{ name }}',
    'ai_o11y-archetype': 'per-user-pattern',
    'ai_o11y-persona': '{{ persona_id }}',
  };
  const res = http.post(`${BASE_URL}/chat`, payload, { headers });
  check(res, { 'request accepted': (r) => r.status < 500 });
  sleep(1);
}

export function fireBaseline() {
  const persona = BASELINE_PERSONAS[Math.floor(Math.random() * BASELINE_PERSONAS.length)];
  const payload = JSON.stringify({
    message: 'help me with my order please',
    user_id: persona,
    session_id: `s-${persona}-${Date.now()}`,
    metadata: { usecase: '{{ name }}', archetype: 'per-user-pattern' },
  });
  const headers = {
    'Content-Type': 'application/json',
    'ai_o11y-usecase': '{{ name }}',
    'ai_o11y-archetype': 'per-user-pattern',
    'ai_o11y-persona': persona,
  };
  http.post(`${BASE_URL}/chat`, payload, { headers });
  sleep(1);
}
