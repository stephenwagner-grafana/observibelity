// Gift-finder loadgen — drives real gift queries through nc-gift-finder so
// the model-winner ATC and quality-trend panels have continuous signal that
// matches what the demo audience sees when they hand-type a query.
//
// Each iteration:
//   1. Build a realistic gift prompt (recipient + budget + interest).
//   2. POST /chat — routes to nc-gift-finder via the gift-keyword detector.
//   3. Pick the first returned product_id.
//   4. POST the add_to_cart tool directly with the model + agent_name labels
//      from the /chat response so `nc_cart_add_total{model, agent_name}` and
//      the structured `atc_event` log line both populate per-model.
//
// Provider routing matches baseline.js's 90% Ollama / 10% Claude split via
// pickModelRouting(persona, hour). Previously this scenario hard-pinned
// provider_override='anthropic', which made every nc-gift-finder
// conversation on the Sigil Conversations page show Claude — masking the
// model-mix story.

import http from 'k6/http';
import { check, sleep } from 'k6';

// Run alongside baseline.js (60s loop, vus pacing). The k6-traffic entrypoint
// iterates /etc/k6/scripts/*.js alphabetically and runs each script to
// completion before sleeping — long-duration scenarios block the queue.
export const options = {
  vus: parseInt(__ENV.K6_GIFT_VUS || '3', 10),
  duration: __ENV.K6_GIFT_DURATION || '60s',
  thresholds: {
    http_req_failed: ['rate<0.80'],
  },
};

const NEONCART = __ENV.NEONCART_URL || 'http://neoncart.observibelity.svc.cluster.local';
const TOOL_URL = __ENV.ADD_TO_CART_URL || 'http://add-to-cart.observibelity.svc.cluster.local/v1/invoke';

// ── Provider/model routing — mirrors baseline.js ──────────────────────
// 90% Ollama, 10% Claude (weighted 60% Haiku / 30% Sonnet / 10% Opus
// inside Claude). Same bucket key (persona + UTC hour) → same model for
// every iteration in the same conversation. See baseline.js for the
// rationale on per-conversation model stability.
const CLAUDE_MODELS = [
  'claude-haiku-4-5-20251001', 'claude-haiku-4-5-20251001',
  'claude-haiku-4-5-20251001', 'claude-haiku-4-5-20251001',
  'claude-haiku-4-5-20251001', 'claude-haiku-4-5-20251001',
  'claude-sonnet-4-6', 'claude-sonnet-4-6', 'claude-sonnet-4-6',
  'claude-opus-4-7',
];
const CLAUDE_FRACTION = parseFloat(__ENV.LOADGEN_CLAUDE_FRACTION || '0.10');

function _hash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h) + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

function pickModelRouting(persona) {
  const now = new Date();
  const bucket = persona + ':' + now.getUTCFullYear() + '-' +
                 (now.getUTCMonth() + 1) + '-' + now.getUTCDate() + '-' +
                 now.getUTCHours();
  const h = _hash(bucket);
  const r01 = (h % 10000) / 10000;
  if (r01 < CLAUDE_FRACTION) {
    return {
      provider_override: 'anthropic',
      model_override: CLAUDE_MODELS[h % CLAUDE_MODELS.length],
    };
  }
  return { provider_override: 'ollama', model_override: null };
}

const RECIPIENTS = [
  { who: 'my 10-year-old nephew', budget: 50, interest: 'gaming' },
  { who: 'my dad', budget: 200, interest: 'audio' },
  { who: 'my wife', budget: 300, interest: 'wearables' },
  { who: 'my best friend', budget: 100, interest: 'peripherals' },
  { who: 'my brother', budget: 150, interest: 'gaming' },
  { who: 'my colleague', budget: 75, interest: 'desk accessories' },
  { who: 'my mom', budget: 250, interest: 'smart home' },
  { who: 'my sister', budget: 120, interest: 'mobile' },
  { who: 'my partner', budget: 400, interest: 'audio' },
  { who: 'my boss', budget: 80, interest: 'desk' },
];

const OCCASIONS = [
  'birthday', 'anniversary', 'holiday', 'wedding', 'graduation', 'just because',
];

function pickRecipient() { return RECIPIENTS[Math.floor(Math.random() * RECIPIENTS.length)]; }
function pickOccasion() { return OCCASIONS[Math.floor(Math.random() * OCCASIONS.length)]; }

function buildMessage() {
  const r = pickRecipient();
  const o = pickOccasion();
  const template = Math.floor(Math.random() * 4);
  if (template === 0) {
    return `Looking for a ${o} gift for ${r.who} under $${r.budget}, they like ${r.interest}`;
  }
  if (template === 1) {
    return `${o} present for ${r.who}, budget about $${r.budget}, into ${r.interest}`;
  }
  if (template === 2) {
    return `Need a gift for ${r.who} - ${r.interest} fan - around $${r.budget}`;
  }
  return `Help me find a gift under $${r.budget} for ${r.who} who loves ${r.interest}`;
}

export default function () {
  const message = buildMessage();
  const sessionId = `gf-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const userId = `customer.gift${Math.floor(Math.random() * 80)}`;
  const routing = pickModelRouting(userId);

  const chatBody = {
    message,
    session_id: sessionId,
    persona_id: userId,
    provider_override: routing.provider_override,
    traffic_origin: 'continuous',
    usecase: 'model-winner',
    // Force routing in case the keyword detector misses an edge phrase.
    agent: 'gift-finder',
  };
  if (routing.model_override) {
    chatBody.model_override = routing.model_override;
  }

  const chatRes = http.post(
    `${NEONCART}/chat`,
    JSON.stringify(chatBody),
    { headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' } },
  );
  if (!check(chatRes, { 'chat 2xx': (r) => r.status >= 200 && r.status < 300 })) {
    sleep(1);
    return;
  }

  let body;
  try { body = chatRes.json(); } catch (_) { sleep(1); return; }
  const products = (body && body.products) || [];
  const model = (body && body.model) || '';
  const agentName = body && body.agent === 'gift-finder' ? 'nc-gift-finder' : 'nc-chatbot';
  if (!products.length) { sleep(1); return; }

  // Convert ~70% of the time so the leaderboard has both buys and skips.
  if (Math.random() > 0.30) {
    const top = products[0];
    const note = `gift idea for ${message.slice(0, 60)}`;
    http.post(
      TOOL_URL,
      JSON.stringify({
        product_id: top.id,
        sku: top.sku,
        qty: 1,
        persona_id: userId,
        agent_name: agentName,
        model: model,
        source: 'loadgen',
        note,
      }),
      {
        headers: {
          'Content-Type': 'application/json',
          'X-Caller': agentName,
          'X-Persona-Id': userId,
        },
      },
    );
  }

  sleep(0.4);
}
