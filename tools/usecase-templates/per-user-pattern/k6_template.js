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

// Honor 429 + Retry-After from llm-gateway. When both providers are at
// capacity the gateway returns 429 with a Retry-After header (seconds);
// we sleep for that interval to yield the VU so retry storms don't pile
// up. We do NOT retry the same request — k6's constant-arrival-rate
// will simply admit the next iteration when the VU becomes free.
function postWithBackoff(url, body, params) {
  const r = http.post(url, body, params);
  if (r.status === 429) {
    let retryAfter = parseFloat(r.headers['Retry-After'] || '5');
    if (isNaN(retryAfter) || retryAfter < 0.1) retryAfter = 5;
    if (retryAfter > 30) retryAfter = 30;  // cap so cycles don't go silly long
    sleep(retryAfter);
  }
  return r;
}

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
// Domain policy: SupportBot users are @acme.com employees; NeonCart users
// are public consumer domains. The per-app filler lists below keep that
// separation in baseline traffic so dashboards reading user.id stay
// internally consistent.
const BASELINE_PERSONAS = '{{ app }}' === 'supportbot'
  ? ['base.a@acme.com', 'base.b@acme.com', 'base.c@acme.com', 'base.d@acme.com']
  : ['base.a@gmail.com', 'base.b@hotmail.com', 'base.c@yahoo.com', 'base.d@aim.com'];

export function fireOffender() {
  const msg = PATTERN_MESSAGES[Math.floor(Math.random() * PATTERN_MESSAGES.length)];
  const payload = JSON.stringify({
    message: msg,
    persona_id: '{{ persona_id }}',
    usecase: '{{ name }}',
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
  const res = postWithBackoff(`${BASE_URL}/chat`, payload, { headers });
  check(res, { 'request accepted': (r) => r.status < 500 });
  sleep(1);
}

export function fireBaseline() {
  const persona = BASELINE_PERSONAS[Math.floor(Math.random() * BASELINE_PERSONAS.length)];
  const payload = JSON.stringify({
    message: 'help me with my order please',
    persona_id: persona,
    usecase: '{{ name }}',
    session_id: `s-${persona}-${Date.now()}`,
    metadata: { usecase: '{{ name }}', archetype: 'per-user-pattern' },
  });
  const headers = {
    'Content-Type': 'application/json',
    'ai_o11y-usecase': '{{ name }}',
    'ai_o11y-archetype': 'per-user-pattern',
    'X-Persona-Id': persona,
  };
  postWithBackoff(`${BASE_URL}/chat`, payload, { headers });
  sleep(1);
}
