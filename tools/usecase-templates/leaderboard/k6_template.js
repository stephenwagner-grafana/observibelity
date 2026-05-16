// k6 scenario template: leaderboard archetype
// Generated for use case: {{ name }}
// App target:           {{ app }}
// Rank by:              {{ rank_by }}
// Grouped by:           {{ group_by }}
//
// Generates baseline traffic at {{ baseline_rate }}/min spread across
// every category in CATEGORIES so the leaderboard always has signal.

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
    '{{ name }}_leaderboard': {
      executor: 'constant-arrival-rate',
      rate: {{ baseline_rate }},
      timeUnit: '1m',
      duration: '60s',
      preAllocatedVUs: 4,
      maxVUs: 12,
      exec: 'fire',
    },
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://{{ app }}.observibelity.svc.cluster.local';
const CATEGORIES = {{ categories }};

const SAMPLE_MESSAGES = [
  'summarize this support thread',
  'what is your return policy',
  'help me pick a plan',
  'i want a refund please',
  'compare your top three skus',
  'reset my password',
];

function pickCategory() {
  return CATEGORIES[Math.floor(Math.random() * CATEGORIES.length)];
}

function pickMessage() {
  return SAMPLE_MESSAGES[Math.floor(Math.random() * SAMPLE_MESSAGES.length)];
}

// Domain policy: SupportBot users are @acme.com; NeonCart users are public.
const PERSONA_DOMAIN = '{{ app }}' === 'supportbot' ? 'acme.com' : 'gmail.com';

export function fire() {
  const category = pickCategory();
  const persona = `customer${Math.floor(Math.random() * 50)}@${PERSONA_DOMAIN}`;
  const payload = JSON.stringify({
    message: pickMessage(),
    persona_id: persona,
    usecase: '{{ name }}',
    session_id: `s-${persona}-${Math.floor(Date.now() / 30000)}`,
    metadata: {
      usecase: '{{ name }}',
      archetype: 'leaderboard',
      group_by: '{{ group_by }}',
      category: category,
    },
  });
  const headers = {
    'Content-Type': 'application/json',
    'ai_o11y-usecase': '{{ name }}',
    'ai_o11y-archetype': 'leaderboard',
    'ai_o11y-group-by': '{{ group_by }}',
    'ai_o11y-category': category,
  };
  const res = postWithBackoff(`${BASE_URL}/chat`, payload, { headers });
  check(res, { 'request accepted': (r) => r.status < 500 });
  sleep(1);
}
