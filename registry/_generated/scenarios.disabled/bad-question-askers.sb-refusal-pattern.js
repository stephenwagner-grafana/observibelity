// k6 scenario template: leaderboard archetype
// Generated for use case: {{ name }}
// App target:           {{ app }}
// Rank by:              {{ rank_by }}
// Grouped by:           {{ group_by }}
//
// Generates baseline traffic at {{ baseline_rate }}/min spread across
// every category in CATEGORIES so the leaderboard always has signal.

import http from 'k6/http';
import { check, sleep } from 'k6/check';

export const options = {
  scenarios: {
    {{ name }}_leaderboard: {
      executor: 'constant-arrival-rate',
      rate: {{ baseline_rate }},
      timeUnit: '1m',
      duration: '24h',
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

export function fire() {
  const category = pickCategory();
  const payload = JSON.stringify({
    message: pickMessage(),
    user_id: `customer${Math.floor(Math.random() * 50)}@acme.com`,
    session_id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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
  const res = http.post(`${BASE_URL}/chat`, payload, { headers });
  check(res, { 'request accepted': (r) => r.status < 500 });
  sleep(1);
}
