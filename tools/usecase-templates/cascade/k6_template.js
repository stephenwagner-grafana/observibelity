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
import { check, sleep } from 'k6/check';

export const options = {
  scenarios: {
    '{{ name }}_cascade_arc': {
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: '10m',
      duration: '24h',
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
      user_id: 'u-{{ cascade_persona }}',
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
      'ai_o11y-persona': 'u-{{ cascade_persona }}',
      'ai_o11y-session': sessionId,
      'ai_o11y-cascade-step': String(i + 1),
    };
    const res = http.post(`${BASE_URL}/chat`, payload, { headers });
    check(res, { 'cascade step accepted': (r) => r.status < 500 });
    sleep(CASCADE_INTERVAL);
  }
}
