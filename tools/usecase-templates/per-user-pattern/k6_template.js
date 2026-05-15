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
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    '{{ name }}_offender': {
      executor: 'constant-arrival-rate',
      rate: {{ weight }},
      timeUnit: '1m',
      duration: '60s',
      preAllocatedVUs: 4,
      maxVUs: 12,
      exec: 'fireOffender',
    },
    '{{ name }}_baseline': {
      executor: 'constant-arrival-rate',
      rate: 6,
      timeUnit: '1m',
      duration: '60s',
      preAllocatedVUs: 4,
      maxVUs: 16,
      exec: 'fireBaseline',
    },
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://{{ app }}.observibelity.svc.cluster.local';
// PATTERN_MESSAGES is a JSON array literal rendered from `message_templates`
// (a list) when the YAML supplies one, falling back to a single-element list
// containing `{{ message_template }}`. Use-case authors should override
// `message_templates` in scenario `params` with keyword-rich phrases so
// dashboard Loki regex panels can match the offender stream.
const PATTERN_MESSAGES = {{ message_templates }};
const BASELINE_PERSONAS = ['u-base-a', 'u-base-b', 'u-base-c', 'u-base-d'];

export function fireOffender() {
  const msg = PATTERN_MESSAGES[Math.floor(Math.random() * PATTERN_MESSAGES.length)];
  const payload = JSON.stringify({
    message: msg,
    persona_id: '{{ persona_id }}',
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
    'X-Persona-Id': '{{ persona_id }}',
  };
  const res = http.post(`${BASE_URL}/chat`, payload, { headers });
  check(res, { 'request accepted': (r) => r.status < 500 });
  sleep(1);
}

export function fireBaseline() {
  const persona = BASELINE_PERSONAS[Math.floor(Math.random() * BASELINE_PERSONAS.length)];
  const payload = JSON.stringify({
    message: 'help me with my order please',
    persona_id: persona,
    session_id: `s-${persona}-${Date.now()}`,
    metadata: { usecase: '{{ name }}', archetype: 'per-user-pattern' },
  });
  const headers = {
    'Content-Type': 'application/json',
    'ai_o11y-usecase': '{{ name }}',
    'ai_o11y-archetype': 'per-user-pattern',
    'X-Persona-Id': persona,
  };
  http.post(`${BASE_URL}/chat`, payload, { headers });
  sleep(1);
}
