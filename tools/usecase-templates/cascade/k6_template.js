// k6 scenario template: cascade archetype
// Generated for use case: {{ name }}
// App target:           {{ app }}
// Counter:              {{ counter_metric }}
// Threshold:            {{ threshold }} per {{ window }}
// Cascade persona:      u-{{ cascade_persona }}
//
// One cascade arc fires every 10 minutes. Each arc walks through
// CASCADE_MESSAGES inside a single session, accumulating the counter
// past the threshold. Sticky persona u-{{ cascade_persona }} runs the arc.

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
    '{{ name }}_cascade_arc': {
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: '10m',
      duration: '60s',
      preAllocatedVUs: 1,
      maxVUs: 2,
      exec: 'runCascadeArc',
    },
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://{{ app }}.observibelity.svc.cluster.local';
const CASCADE_MESSAGES = {{ cascade_messages }};
const CASCADE_INTERVAL = {{ cascade_interval }};

export function runCascadeArc() {
  const sessionId = `s-cascade-{{ cascade_persona }}-${Date.now()}`;
  for (let i = 0; i < CASCADE_MESSAGES.length; i++) {
    const payload = JSON.stringify({
      message: CASCADE_MESSAGES[i],
      persona_id: 'u-{{ cascade_persona }}',
      usecase: '{{ name }}',
      session_id: sessionId,
      metadata: {
        usecase: '{{ name }}',
        archetype: 'cascade',
        step: i + 1,
        of: CASCADE_MESSAGES.length,
      },
    });
    const headers = {
      'Content-Type': 'application/json',
      'ai_o11y-usecase': '{{ name }}',
      'ai_o11y-archetype': 'cascade',
      'X-Persona-Id': 'u-{{ cascade_persona }}',
      'ai_o11y-session': sessionId,
      'ai_o11y-cascade-step': String(i + 1),
    };
    const res = postWithBackoff(`${BASE_URL}/chat`, payload, { headers });
    check(res, { 'cascade step accepted': (r) => r.status < 500 });
    sleep(CASCADE_INTERVAL);
  }
}
