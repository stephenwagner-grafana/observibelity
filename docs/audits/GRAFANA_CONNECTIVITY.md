# Grafana Cloud Connectivity Report — ObserVIBElity v0.3.0

**Date:** 2026-05-13
**Cluster:** k3s home cluster, namespace `observibelity`
**Helm release:** `observibelity-0.3.0`
**Result:** **OTel collector is exporting, but Grafana Cloud is rejecting all traces/logs with HTTP 502** because the deployment is pointing at the wrong Grafana Cloud region. **One-line fix available.**

---

## TL;DR

| Signal       | Pipeline                            | Status                                                                                |
|--------------|-------------------------------------|---------------------------------------------------------------------------------------|
| Metrics      | Grafana Cloud Kubernetes Integration (kube-state-metrics, cadvisor) | **OK** — scraping the `observibelity` namespace.                |
| Logs         | Grafana Cloud Alloy log scraper (cluster-wide stdout collection)   | **OK** — observibelity stdout logs landing in Loki.             |
| **OTLP traces**  | otel-collector → `otlp-gateway-prod-us-east-0.grafana.net`     | **BROKEN — HTTP 502** (stack lives in `us-east-2`, not `us-east-0`).  |
| **OTLP logs**    | otel-collector → `otlp-gateway-prod-us-east-0.grafana.net`     | **BROKEN — HTTP 502** (same root cause).                              |
| **OTLP metrics** | otel-collector → `otlp-gateway-prod-us-east-0.grafana.net`     | No emitters wired up yet; would also fail if any.                     |

---

## 1. Grafana Cloud stack

The supplied API token (`glsa_TMX1...`) is a **stack-scoped service account token** (NOT a Grafana Cloud org token), so the `https://grafana.com/api/instances` org-level call returns `401 InvalidCredentials`. That is expected.

Querying the stack directly via the Grafana MCP gateway (which the token DOES grant access to) resolves the stack identity from the datasource list (UIDs prefixed with `grafanacloud-stephenwagner-...`):

- **Stack slug:** `stephenwagner`
- **Stack URL:** `https://stephenwagner.grafana.net`
- **Stack instance ID (Grafana Cloud):** `1372178` (matches the value in the `otel-grafanacloud-creds` k8s secret)
- **Stack region (actual):** **`prod-us-east-2`** — confirmed by direct auth test against every OTLP gateway endpoint (see Section 4).
- **Configured region (in ObserVIBElity Helm chart):** `prod-us-east-0` — **wrong region.**

### Datasources (confirmed reachable)

| Datasource UID                  | Type        | Notes                                                                |
|---------------------------------|-------------|----------------------------------------------------------------------|
| `grafanacloud-prom`             | Prometheus  | Mimir; default datasource. Auth OK.                                  |
| `grafanacloud-logs`             | Loki        | Auth OK; observibelity logs visible.                                 |
| `grafanacloud-traces`           | Tempo       | Auth OK; zero observibelity traces (because OTLP gateway is 502-ing).|
| `grafanacloud-profiles`         | Pyroscope   | Reachable.                                                           |
| `grafanacloud-alert-state-history` | Loki     | Reachable.                                                           |

(Full list — 28 datasources — available via `mcp__grafana__list_datasources`.)

---

## 2. What telemetry is flowing — by signal

### 2a. Logs (Loki) — **WORKING**, via a side channel

`observibelity` namespace logs ARE landing in Loki, but **NOT through the otel-collector**. They are scraped by the cluster's pre-existing Grafana Cloud Kubernetes Monitoring (Alloy) log collector, which tails stdout from every pod and ships to Loki directly. Log line counts over a 15-minute window (`{namespace="observibelity"}`):

```
container               lines
specialist              5596
tool                    8056
supportbot              1168
neoncart                 625
seed                     191
llm-gateway              145
seed-manual               75
postgres                  44
otel-collector            32
migrate                    8
wait-for-postgres          4
```

Total ≈ 16k log lines / 15 min. Labels present: `namespace=observibelity`, `cluster=k3s`, `container=*`, `pod=*`, `service_namespace=observibelity`, `service_name=observibelity` (note: `service_name` here is the Helm release name, NOT the per-pod service.name — this is set by Alloy's discovery, not by OTLP).

### 2b. Metrics (Mimir) — **PARTIAL**, no OTLP

`{namespace="observibelity"}` returns scraped metrics from `kube-state-metrics`, `cadvisor`, and `opencost` integrations (the cluster-wide GC Kubernetes Monitoring scrape). Roughly:

```
job                                          series
integrations/kubernetes/kube-state-metrics     1833
integrations/kubernetes/cadvisor                488
integrations/opencost                            39
integrations/kubernetes/kubelet                   9
```

**No application-level metrics from ObserVIBElity itself are in Mimir.** Specifically:
- `up{namespace="observibelity"}` returns 0 series (because Mimir does not scrape pods in this namespace — only the cluster-wide integrations).
- `{service_namespace="observibelity"}` returns 0 application metrics.
- `{service_name="llm-gateway"}` returns 0.
- `otelcol_*` self-metrics from the new collector are not in Mimir either.

The intended path (otel-collector OTLP push → Mimir via `otlp-gateway`) is broken (see Section 4).

### 2c. Traces (Tempo) — **NONE**

Zero traces for `resource.service.namespace="observibelity"`, `resource.deployment.environment="observibelity"`, or `resource.service.name="manual-test"` (the synthetic test span set we sent, see Section 5).

### 2d. llm-gateway is producing OTel-flavored JSON but spans are empty

llm-gateway log lines include `"trace_id": ""` and `"span_id": ""` — i.e., the structured log fields are emitted but no active OTel span context exists. The pod's environment variables ARE set correctly:

```
OTEL_SERVICE_NAME=llm-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_RESOURCE_ATTRIBUTES=service.name=llm-gateway,service.namespace=observibelity
```

And the OTel Python libraries are installed (`opentelemetry-sdk 1.41.1`, `opentelemetry-instrumentation-fastapi 0.62b1`, `opentelemetry-exporter-otlp 1.41.1`). However, the SDK is **not being initialized** by the app at startup (no `TracerProvider` set up, no autoinstrumentation entrypoint enabled). This is a **separate bug from the gateway-region issue** and needs to be addressed in the llm-gateway image / startup wiring before any traces will be produced even after the region fix.

---

## 3. otel-collector pod — config & status

- **Pod:** `otel-collector-555558968-4l4xc`, `1/1 Running`, 0 restarts.
- **Image:** `otel/opentelemetry-collector-contrib:0.96.0`
- **Labels:** `app.kubernetes.io/component=otel-collector`, `app.kubernetes.io/name=observibelity` (note: the `app.kubernetes.io/name` is `observibelity`, NOT `otel-collector` — the kubectl selector in the task spec `-l app.kubernetes.io/name=otel-collector` does not match).
- **ConfigMap:** `otel-collector-config` is correct — receivers `otlp/grpc:4317` + `otlp/http:4318`, processors `memory_limiter, resourcedetection/env, batch`, exporter `otlphttp/grafanacloud` with the basic-auth header set from secret `otel-grafanacloud-creds`.
- **Pipelines:** `traces`, `metrics`, `logs` all wired with the same processors + exporter.
- **Self-metrics endpoint:** `:8888/metrics` is enabled in config but **not exposed in the Service** (Service only exposes `4317/4318/13133`). Could not scrape from outside the pod; the container image has no `wget`/`curl`/`which` available, so we could not curl localhost:8888 from inside either. **Recommendation:** add `8888/TCP` to the otel-collector Service and add a ServiceMonitor (or add `prometheus` exporter wired into the metrics pipeline so the collector's own health shows up in Mimir).

---

## 4. The 502 error — root cause

After triggering test traffic (5x `POST /v1/complete` against llm-gateway via `kubectl port-forward`) AND manually shipping 5 OTLP spans from inside the cluster (`opentelemetry-sdk` Python client → `http://otel-collector:4318`), the collector's logs immediately show:

```
2026-05-13T04:22:20.447Z info exporterhelper/retry_sender.go:118 Exporting failed. Will retry the request after interval.
  {"kind": "exporter", "data_type": "traces", "name": "otlphttp/grafanacloud",
   "error": "Throttle (0s), error: error exporting items, request to
            https://otlp-gateway-prod-us-east-0.grafana.net/otlp/v1/traces
            responded with HTTP Status Code 502", "interval": "6.378587751s"}
```

Same error for `data_type: logs`. Retries keep backing off.

Direct curl with the same basic-auth header (`Authorization: Basic <base64(1372178:glc_...)>`):

```
POST https://otlp-gateway-prod-us-east-0.grafana.net/otlp/v1/traces
→ HTTP 502
   {"status":"error","errorType":"unavailable",
    "error":"dial tcp: lookup cortex-gw-internal.tempo-prod-26.svc.cluster.local.
             on 10.50.0.10:53: no such host"}
```

The gateway is in the **wrong region's** Tempo cluster and cannot resolve the backend.

Auth-probe across all GC regions with the exact same creds (`1372178:glc_...`):

| Endpoint                                       | Result                                  |
|------------------------------------------------|-----------------------------------------|
| `otlp-gateway-prod-us-east-0.grafana.net`      | 502 — DNS lookup to `tempo-prod-26`     |
| `otlp-gateway-prod-us-east-1.grafana.net`      | 401 — invalid credentials               |
| **`otlp-gateway-prod-us-east-2.grafana.net`**  | **200 — credentials accepted**          |
| `otlp-gateway-prod-us-central-0.grafana.net`   | 401                                     |
| `otlp-gateway-prod-us-west-0.grafana.net`      | 401                                     |
| `otlp-gateway-prod-eu-west-2.grafana.net`      | 401                                     |
| `otlp-gateway-prod-eu-west-3.grafana.net`      | 401                                     |

**The stack lives in `prod-us-east-2`.** The Helm chart's default of `us-east-0` is wrong for this account.

### Fix

`/workspace/observibelity/values-deploy.yaml:38`:

```yaml
otlpEndpoint: "https://otlp-gateway-prod-us-east-0.grafana.net/otlp"
```

→ change to:

```yaml
otlpEndpoint: "https://otlp-gateway-prod-us-east-2.grafana.net/otlp"
```

After `helm upgrade`, the collector will pick up the new config (or restart the otel-collector pod to be sure). Verification:

1. `kubectl logs -n observibelity -l app.kubernetes.io/component=otel-collector --since=2m | grep -E "Exporting failed|HTTP Status"` should be empty.
2. Re-send manual spans (the Python snippet at the bottom of this report) and confirm in Tempo: `{resource.service.name="manual-test"}`.

### Side note: the chart's region default should be configurable per stack

The fact that this is a hardcoded default in `values-deploy.yaml` means the install will be broken for **any** Grafana Cloud customer whose stack is not in `us-east-0`. Per the planner's "2-command deploy" goal, this needs to either:
- be auto-detected from the API token (call the Grafana Cloud stack details API to determine `regionSlug`), OR
- be a required input in the wizard / `install.sh` prompt.

---

## 5. Synthetic OTLP test we ran (for the report)

```bash
kubectl exec -n observibelity llm-gateway-5888fb6988-sw2b8 -- python3 -c "
import os
os.environ['OTEL_SERVICE_NAME']='manual-test'
os.environ['OTEL_EXPORTER_OTLP_ENDPOINT']='http://otel-collector.observibelity.svc.cluster.local:4318'
os.environ['OTEL_EXPORTER_OTLP_PROTOCOL']='http/protobuf'
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
prov = TracerProvider(resource=Resource.create({
    'service.name':'manual-test', 'service.namespace':'observibelity'}))
prov.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(prov)
tr = trace.get_tracer('manual-test')
for i in range(5):
    with tr.start_as_current_span(f'manual-test-span-{i}') as s:
        s.set_attribute('test.iter', i)
        s.set_attribute('ai_o11y.usecase','smoke-test-manual')
prov.shutdown()
print('SENT 5 manual spans')
"
```

Result: collector received the 5 spans, attempted to export, hit HTTP 502 on the `us-east-0` gateway, and queued for retry (still queued at end of investigation).

---

## 6. Reuse of existing AI o11y dashboards

The user's stack already contains a rich set of AI o11y dashboards from the previous demo:

| UID                          | Title                                                          | Folder              |
|------------------------------|----------------------------------------------------------------|---------------------|
| `ai-o11y-demo-agenda`        | AI O11y — Demo Agenda                                          | (root)              |
| `ai-obs-use-case-selector`   | AI Observability — Use Case Builder (centerpiece)              | AI O11y             |
| `ai-obs-use-case-builder`    | AI Observability — Use Case Builder                            | AI Observability    |
| `ai-obs-use-case-overviews`  | AI Observability — Use Case Overviews                          | AI Observability    |
| `ai-obs-app-neoncart`        | AI Observability — NeonCart                                    | AI O11y             |
| `ai-obs-playbook-neoncart`   | AI Observability — NeonCart Playbook                           | AI Observability    |
| `neoncart-ai-rca-conv`       | NeonCart — AI RCA (Single Conversation)                        | AI Observability    |
| `neoncart-ai-business`       | NeonCart — AI Business KPIs                                    | (root)              |
| `neoncart-ai-o11y`           | NeonCart — AI Observability RCA                                | (root)              |
| `neoncart-convos`            | NeonCart — AI Operations                                       | (root)              |
| `neoncart-demo`              | NeonCart Demo — SRE Failure + AI Behavior                      | (root)              |
| `app-o11y-neoncart`          | Application Observability — NeonCart                           | PepsiCo             |

**Reusability assessment:** The label conventions match the planner's commitment (per `/home/claude/.claude/projects/-workspace/memory/observibelity/planner_and_decisions.md`), specifically `service.namespace`, `service.name`, `ai_o11y.usecase`, `ai_o11y.specialist`, `gen_ai.*`. HOWEVER none of these dashboards will populate against the current ObserVIBElity deploy because:
1. No OTLP signals are reaching Mimir/Tempo (the 502 issue).
2. The previous demo used `namespace=neoncart` and `namespace=supportbot`, NOT `namespace=observibelity` — so dashboards that hardcode `namespace="neoncart"` will not show ObserVIBElity data even after the OTLP pipe is fixed. Dashboards that use `service.namespace` (the OTel resource attribute) WILL work because the chart sets `OTEL_RESOURCE_ATTRIBUTES=service.namespace=observibelity,deployment.environment=observibelity`.

The ObserVIBElity chart ships its own copy of 13 dashboard JSONs under `/workspace/observibelity/dashboards/` (`ai-obs-app-neoncart.json`, `ai-obs-app-supportbot.json`, `ai-obs-best-models.json`, `ai-obs-cascade-spike.json`, `ai-obs-compliance.json`, `ai-obs-conv.json`, `ai-obs-cost.json`, `ai-obs-data-theft.json`, `ai-obs-evals.json`, `ai-obs-ground.json`, `ai-obs-pii.json`, `ai-obs-tools.json`, `README.md`) — these are intended to be the canonical set for this packaged release and should be installed via the chart, NOT relied on from the existing stack. Per the planner's "GitHub-canonical" decision, the chart's bundled dashboards are the source of truth; the existing stack dashboards are reference copies from the old demo and may diverge.

---

## 7. Secondary issues observed (not connectivity, but blocking demo)

These are NOT Grafana connectivity issues but were noticed during this investigation:

- **17 specialist/tool pods are in CrashLoopBackOff.** Root cause: `ModuleNotFoundError: No module named 'cachetools'` — the `tool_base` package imports `cachetools` but the specialist/tool images do not have it installed.
  - `create-expense`, `create-ticket`, `geo-lookup`, `get-employee`, `get-employee-history`, `get-inventory`, `get-order-history`, `get-product`, `get-ticket`, `kb-search`, `list-tickets`, `nc-chatbot`, `nc-fraud-detector`, `nc-fulfillment-orchestrator`, `place-order`, `request-access`, `reset-password`, `sb-employee-info`, `sb-escalator`, `sb-expense-helper`, `sb-hiring-helper`, `sb-hr-info`, `sb-it-troubleshoot` — all crashing on the same import.
  - **Fix:** add `cachetools` to the tool/specialist Docker image requirements.
- **neoncart pod runs but throws Jinja2 `TypeError: unhashable type: 'dict'`** on every request — template cache key bug.

These are tracked separately as part of the v0.3.0 deploy task.

---

## 8. Exit-criteria summary

- **Is otel-collector exporting?** Yes — it receives OTLP and attempts to ship.
- **Is it succeeding?** **No.** Every export attempt returns HTTP 502 from `otlp-gateway-prod-us-east-0.grafana.net` because the stack actually lives in `prod-us-east-2`.
- **One-line fix:** `/workspace/observibelity/values-deploy.yaml:38` — change region from `us-east-0` to `us-east-2`, `helm upgrade`, and the export pipe will come up.
- **Secondary OTLP work required even after the fix:** llm-gateway (and presumably the specialists once they stop crashing) is not initializing the OTel SDK — `trace_id`/`span_id` are empty in app logs. Autoinstrumentation needs to be wired in at app startup before traces will be produced.

---

## Appendix: cleanup actions performed

- Port-forward `svc/llm-gateway 8001:80` was started, used for 5 test requests, and terminated (exited cleanly when the bash subshell ended).
- No persistent state was left behind in the cluster.
