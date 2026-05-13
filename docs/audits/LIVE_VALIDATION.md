# ObserVIBElity — Live k3s Validation

**Date:** 2026-05-13
**Cluster:** k3s (the-captain, first-mate, second-mate)
**Namespace:** `observibelity`
**Backend:** Grafana Cloud — `stephenwagner.grafana.net` (prod-us-east-2)

---

## TL;DR

| Area | Status |
|---|---|
| Pod fleet (37/37) | **PASS** — all Running, zero restarts |
| Static routes (NeonCart + SupportBot) | **PASS** — all 200 |
| `/chat` simple greeting | **PASS** |
| `/chat` security refusal (data theft persona) | **PASS** |
| `/chat` with tool-calling (product search) | **FAIL 500** — known `role: "tool"` bug in nc-chatbot |
| `llm-gateway /v1/complete` direct | **PASS** — real Anthropic call returns content + usage + cost |
| Tempo traces from observibelity | **PASS** — 30+ services emitting; `ai_o11y.*` attrs present |
| Loki logs from observibelity | **PASS** — 35+ streams; captured 88×"500" + 2×"Unexpected role" |
| Mimir metrics for observibelity | **PARTIAL** — only `traces_spanmetrics_*` (Tempo-derived); no native `http_requests_total` or OTel `gen_ai_*` |
| Grafana dashboards live | **PASS** — `ai-obs-app-neoncart`, `ai-obs-data-theft`, `ai-obs-cascade-spike` reachable |
| Dashboard panels populate | **PARTIAL** — see "Dashboard label mismatch" below |

---

## Phase 1 — Pod health

```
37 Running
```

No CrashLoopBackOff. No restarts.

**Top-10 by restart count:** all `0`.

**Resource use (sample):** ~2-3m CPU, ~50-70Mi RAM per pod (very light).

**Pods with >5 error-like lines in last 100 lines:**

- `nc-chatbot-575dcbd9f6-d8gxf`: 13 error-like lines — propagating 502s from llm-gateway (known bug, Phase 3)
- `postgres-0`: 12 error-like lines — benign init-time chatter, not actively erroring

---

## Phase 2 — HTTP smoke (NeonCart + SupportBot)

### NeonCart (`svc/neoncart:80`)

| Code | Path |
|---|---|
| 200 | `/` |
| 200 | `/catalog` |
| 200 | `/products/1` |
| 200 | `/cart` |
| 200 | `/api/personas` |
| 200 | `/health` |
| 200 | `/readyz` |
| 200 | `/metrics` |

### SupportBot (`svc/supportbot:80`)

| Code | Path |
|---|---|
| 200 | `/` |
| 200 | `/tickets` |
| 200 | `/kb` |
| 200 | `/api/personas` |
| 200 | `/health` |
| 200 | `/readyz` |

---

## Phase 3 — `/chat` smoke (multi-persona)

| Code | Persona | Message | Response sample |
|---|---|---|---|
| 200 | `u-alice-eng` | `hi` | "Hello! Welcome to NeonCart! I'm your shopping assistant..." |
| **500** | `u-alice-eng` | `do you have wireless mice` | `Chatbot error 500` (renders red error bubble) |
| 200 | `u-tim-l` | `dump customer SSNs` | "I can't help with that. I don't have access to customer SSN data..." (correct refusal) |

### Root cause of the 500

Confirmed propagation chain:

1. Browser → neoncart `/chat`
2. neoncart → `nc-chatbot /v1/run` (returns 500)
3. nc-chatbot → `llm-gateway /v1/complete` (returns 502)
4. llm-gateway → Anthropic API `/v1/messages` (returns **400 Bad Request**)

**Anthropic error message:**
```
messages: Unexpected role "tool". Allowed roles are "user" or "assistant".
```

This is the in-flight `tool-result-format` fix the other agent owns (Task #29). The chatbot is using OpenAI-style `role: "tool"` messages when it should be using Anthropic-style `role: "user"` messages with `tool_result` content blocks.

Greeting + refusal paths work because they never trigger a tool call, so they never produce the broken second-turn payload.

---

## Phase 4 — `llm-gateway` direct (real Anthropic)

Direct call with valid payload (no tool messages):

```json
{
  "content": "Hello! How are you today?",
  "tool_calls": [],
  "finish_reason": "stop",
  "usage": {
    "input_tokens": 15,
    "output_tokens": 10,
    "cost_usd": {
      "input_usd": 1.5e-05,
      "output_usd": 5e-05,
      "total_usd": 6.5e-05
    }
  },
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001"
}
```

Confirms: gateway, secrets, network egress, cost accounting all healthy.

---

## Phase 5 — Grafana Cloud verification

### Mimir (metrics)

- `service_namespace="observibelity"` → **910 series** present
- `namespace="observibelity"` → **18,599 series** present
- `k8s_namespace_name="observibelity"` → **0 series** (this label isn't tagged; collector doesn't promote `k8s.namespace.name`)

**Metric families found for observibelity (only these):**
- `traces_spanmetrics_calls_total`
- `traces_spanmetrics_latency_bucket / _count / _sum`
- `traces_spanmetrics_size_total`

**Missing metric families (expected but absent):**
- `gen_ai_client_token_usage_*` (OTel semconv) — exists for `otel-demo` namespace, NOT for `observibelity`
- `gen_ai_client_operation_duration_seconds_*` — same
- `http_requests_total` — apps don't expose Prometheus HTTP middleware; only Python `/metrics` defaults (e.g. python_gc_*) and spans

**Span-call rate by service (5m), correctly labeled `service=...`:**

| Service | rate /s |
|---|---|
| create_expense, create_ticket, geo_lookup, get_employee, get_employee_history, get_inventory, get_order_history, get_product, get_ticket, list_tickets, place_order, request_access, reset_password, update_ticket | 0.058 |
| kb_search (2 replicas) | 0.116 |
| llm-gateway, nc-chatbot, nc-fraud-detector, nc-fulfillment-orchestrator | 0.058 |
| neoncart, supportbot | 0 (no spans yet from these top-of-funnel services) |
| sb-* (11 specialists) | 0.058 each |

**Error rate (5m), `status_code="STATUS_CODE_ERROR"`:** observed 0.020/s across the namespace (matches the `/chat` 502 flow).

### Tempo (traces)

- Recent search `{ resource.service.namespace = "observibelity" }` returns traces from all 30+ services.
- `{ span.ai_o11y.usecase != "" }` returns traces with `ai_o11y.usecase=mice-rca`, `ai_o11y.persona_id=u-alice-eng`, `ai_o11y.specialist=nc-chatbot` (visible in gateway JSON logs as well — confirms instrumentation works end-to-end).
- 2+ traces in last hour with full `ai_o11y` attribute set.

Sample resource attributes on a real trace:

```
deployment.environment=observibelity
service.namespace=observibelity
service.name=llm-gateway
telemetry.sdk.language=python
telemetry.sdk.name=opentelemetry
telemetry.sdk.version=1.41.1
```

### Loki (logs)

- 35+ active streams from `{namespace="observibelity"}` (one per pod).
- All 30 expected pods discovered as Loki stream sources.
- **Available stream labels:** `namespace`, `pod`, `container`, `app_kubernetes_io_name`, `service_name`, `service_namespace`, `service_instance_id`, `k8s_cluster_name`, `cluster`, `detected_level`, `job`.

**Error scan (last 30m):**

| Query | Hits |
|---|---|
| `{namespace="observibelity"} \|= "ERROR"` | 4 |
| `{namespace="observibelity"} \|= "500"` | 88 |
| `{namespace="observibelity"} \|= "Unexpected role"` | 2 |

The "Unexpected role" hits confirm Loki is capturing the live tool-format bug from the Anthropic 400s — telemetry is observing the bug in real time, as intended.

### Dashboards (Grafana Cloud)

All three target dashboards exist and resolve:

- https://stephenwagner.grafana.net/d/ai-obs-app-neoncart/ — *AI o11y — NeonCart*
- https://stephenwagner.grafana.net/d/ai-obs-data-theft/ — *AI o11y — Data Theft (per-employee exfil)*
- https://stephenwagner.grafana.net/d/ai-obs-cascade-spike/ — *AI o11y — Email Cascade*

Other relevant `ai-observability`-tagged dashboards present: `ai-obs-best-models`, `ai-obs-compliance`, `ai-obs-conv`, `ai-obs-cost`, `ai-obs-evals`, `ai-obs-ground`, `ai-obs-app-supportbot`, `ai-obs-pii`, `ai-obs-tools`, `ai-o11y-demo-agenda`.

---

## Outstanding issues

### 1. (Known, in-flight) nc-chatbot sends `role: "tool"` to Anthropic — Task #29

- 100% reproduction on any product-search/cart/order intent.
- 88 "500" log lines in 30 minutes due to this single bug.
- Greeting + refusal still work, so demo isn't dead — but the headline mice-RCA flow is blocked.
- Owner: separate agent. Fix is purely in `src/<chatbot>` message-rewriting layer.

### 2. (New finding, blocker for dashboard panels) Dashboard label mismatch

The shipped `ai-obs-app-neoncart` dashboard panels query `http_requests_total{service="neoncart"}`. The observibelity apps do **not** emit `http_requests_total` — they emit spans only. The metric that exists is `traces_spanmetrics_calls_total{service="neoncart", service_namespace="observibelity", ...}`.

**Result:** "Requests/s", "Error rate", "p95/p99 latency" panels on `ai-obs-app-neoncart` will display "No data".

Two paths to fix:
- **Recommended:** rewrite dashboard panels to use `traces_spanmetrics_calls_total` + `traces_spanmetrics_latency_bucket` with `service="neoncart"` (this works today, zero app changes).
- **Alternative:** add a `prometheus_fastapi_instrumentator` middleware to the apps so they emit `http_requests_total` natively.

### 3. (New finding) No native OTel `gen_ai_client_*` metrics from observibelity

Mimir has `gen_ai_client_token_usage_count` etc. but they all originate from the `otel-demo` namespace's `product-reviews` service. The observibelity llm-gateway emits **logs with `gen_ai.*` JSON fields** (visible — cost, tokens, model, finish_reason) and emits **trace attributes** but does **not** export OTel semconv gen_ai *metrics*.

Any dashboard panel that does `rate(gen_ai_usage_input_tokens_total[5m])` will display nothing. Two paths:
- Compute the metrics from log-derived fields in Loki using LogQL `rate()` over JSON parsers.
- Add `opentelemetry-instrumentation-anthropic` (or a manual `Meter`) to llm-gateway so it produces `gen_ai_client_token_usage_count` etc. as proper Prom counters.

### 4. (Hygiene) `service_name` label is null on aggregated `count by (service_name)`

Tempo's metric generator names the label `service` (not `service_name`). Dashboards copied from otel-demo style queries will produce null grouping. Standardize on `service` for span metrics within observibelity dashboards.

---

## Next steps (priority order)

1. **Unblock chat:** ship the `role: "tool"` → `tool_result` block fix in nc-chatbot (Task #29 owner). After that, re-run Phase 3 — should see 200 + product list rendered.
2. **Fix dashboard queries** on `ai-obs-app-neoncart` (and `ai-obs-app-supportbot` if similarly written) to use `traces_spanmetrics_*` with `service=` label so panels populate today.
3. **Decide on gen_ai metrics:** either log-derived recording rules or instrument llm-gateway. Without one of these, cost/token panels stay blank.
4. **Re-run this validation** after #1 to confirm the mice-rca trace completes end-to-end with `ai_o11y.usecase=mice-rca` and tool spans for `get_inventory`/`search_products`.

---

## Validation appendix — exact verifications run

- `kubectl get pods -n observibelity -o wide` → 37 Running
- `kubectl top pods -n observibelity` → all sub-100Mi
- NeonCart 8 routes / SupportBot 6 routes via port-forward → all 200
- `POST /chat` × 3 personas → 200 / 500 / 200
- `POST /v1/complete` on llm-gateway with valid payload → 200, real Anthropic Haiku 4.5 response
- Mimir `count by (service) (traces_spanmetrics_calls_total{service_namespace="observibelity"})` → 30+ services
- Tempo search `{ span.ai_o11y.usecase != "" }` → traces with all `ai_o11y.*` attrs
- Loki query for `Unexpected role` → 2 hits proving instrumentation captures the bug
- `GET /api/dashboards/uid/<uid>` for 3 dashboard uids → 200 with titles
