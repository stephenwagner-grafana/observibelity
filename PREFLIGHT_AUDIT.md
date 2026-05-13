# Preflight Audit — ObserVIBElity Helm Templates

**Audit date**: 2026-05-13
**Auditor**: Claude (chart audit pass)
**Scope**: `/workspace/observibelity/templates/**` rendered with `values-deploy.yaml` at `phase: 2`
**Goal**: catch latent pod-failure bugs the current deploy round hasn't yet hit.

---

## Severity legend

- **BLOCKER**  — pod will fail on first start; deploy cannot succeed
- **HIGH**     — pod starts but feature is broken / silently mis-configured
- **MEDIUM**   — works today but will bite a future operator
- **LOW**      — cosmetic / dead-code / cleanup

---

## Findings — fixed in place

### F1. `.helmignore` strips `templates/tools/loop.yaml` from the chart  [BLOCKER — FIXED]

**File**: `/workspace/observibelity/.helmignore`
**Symptom**: Zero tool Deployments / Services rendered. Specialists try to call `http://search-products`, `http://kb-search`, etc. and get DNS NXDOMAIN. Every `mice-rca` request fails on the first tool call.
**Root cause**: The bare pattern `tools/` matches at any depth in the chart tree, so it ate `templates/tools/loop.yaml` along with the top-level `tools/` scripts directory. Same pattern bug also dropped `templates/tests/test-connection.yaml`.

Verified by packaging the chart and listing the tarball — `observibelity/templates/tools/` was completely missing.

**Fix applied**: anchored the directory patterns with a leading `/` so they only match at repo root:
```
/seed_data/
/src/
/tests/
/docs/
/wiki/
/tools/
/wizard/
/migrations/
/registry/use_cases/
```
After fix: `helm template` now emits 16 tool Deployments + 16 tool Services, matching `.Values.tools`.

### F2. Tool image names mismatch between chart and build workflow  [BLOCKER — FIXED]

**File**: `/workspace/observibelity/templates/tools/loop.yaml:38`
**Symptom**: Every tool pod would land in `ImagePullBackOff` because the chart asked for `observibelity-search-products:0.3.0` (hyphen) while the GH Actions release/build workflows tag images as `observibelity-search_products:0.3.0` (underscore).
**Root cause**: Templates used `$dnsName` (underscore→hyphen) for both the K8s object name AND the image reference. Object names need DNS-1123 (hyphens); image names need to match what `.github/workflows/{build-images,release}.yml` actually publishes — matrix `name: search_products` → image suffix `search_products`.

**Fix applied**: Tools loop now uses `$name` for the image, `$dnsName` for the Service/Deployment/Pod selector — keeping DNS-safe k8s names while pulling the actual image that exists on GHCR:
```yaml
# Before
image: "{{ ... }}/observibelity-{{ $dnsName }}:{{ ... }}"
# After
image: "{{ ... }}/observibelity-{{ $name }}:{{ ... }}"
```
Confirmed against `release.yml` and `build-images.yml` matrices — every tool now maps to a tag the workflow actually pushes.

### F3. Migrate Job races Postgres bootstrap on first install  [HIGH — FIXED]

**File**: `/workspace/observibelity/templates/jobs/migrate.yaml`
**Symptom**: Helm post-install hooks fire as soon as Helm creates the StatefulSet — they DO NOT wait for the StatefulSet pods to reach `Ready`. Postgres on first start runs `initdb` + creates `POSTGRES_DB` which takes ~30s on a cold node. `alembic upgrade head` errors instantly with "connection refused", the Job burns through `backoffLimit: 3` (each retry roughly 10s), and `helm install --wait --atomic` rolls back the release.
**Root cause**: No init container guarding for Postgres readiness.

**Fix applied**: Added a `wait-for-postgres` init container that polls `pg_isready -h postgres -d observibelity` every 2s for up to 120s, using the same `postgres:16-alpine` image already in the chart (no extra pull). Seed Job does NOT need its own wait because it runs at hook-weight 2 (after migrate), and migrate only succeeds once Postgres is fully ready.

---

## Findings — flagged for the user (Python source, out of scope for chart fixes)

### F4. `llm-gateway` ignores chart-supplied env vars  [HIGH — FLAGGED]

**Files**: `/workspace/observibelity/src/llm-gateway/app/main.py:58-59` + `/workspace/observibelity/templates/llm-gateway/deployment.yaml:50-57`
**Symptom**: The model the operator picks via `values.yaml > llmGateway.providers.anthropic.model` is ignored. Gateway always uses the hardcoded `claude-haiku-4-5-20251001` default.
**Root cause**: Chart sets `ANTHROPIC_DEFAULT_MODEL`, `ANTHROPIC_ENABLED`, `OLLAMA_ENABLED`, `OLLAMA_BASE_URL`, `PRICING_CONFIG_PATH`, `ROUTING_CONFIG_PATH`. The Python code reads only `ANTHROPIC_MODEL`, `ANTHROPIC_API_KEY`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`. The other env vars are dead.

**Fix needed**: either rename the chart env vars to what the code reads, OR teach `_build_provider_configs()` to read the new names. Pricing config (`pricing.json`) and routing config (`routing.json`) in the ConfigMap are also never loaded by the code — the volumeMount is dead until the gateway is taught to honor the env var paths.

### F5. Specialist `TOOL_ALLOWLIST` env var is dead  [LOW — FLAGGED]

**Files**: `/workspace/observibelity/src/specialists/_base/specialist_base/specialist.py:47` + `/workspace/observibelity/templates/specialists/loop.yaml:52`
**Symptom**: Tool allowlists are baked into each subclass at build time; the chart's `TOOL_ALLOWLIST=search_products,get_product,...` env var is informational only. Operators editing `values.yaml > specialists[].tool_allowlist` will see no behavior change without a rebuild.
**Root cause**: `TOOL_ALLOWLIST` is a `ClassVar` on each subclass; nothing reads `os.environ["TOOL_ALLOWLIST"]`.

**Fix needed (optional)**: teach `Specialist.__init__` to merge the env var into `self.TOOL_ALLOWLIST` if set, OR drop the env var from the chart and document that allowlists are source-managed.

### F6. `specialist_base/main.py` doesn't expose `/metrics`  [LOW — FLAGGED]

**File**: `/workspace/observibelity/src/specialists/_base/specialist_base/main.py:50-58`
**Symptom**: Every other component (`neoncart`, `supportbot`, `llm-gateway`, `tool_base`) exposes `/metrics`. Specialists alone do not.
**Root cause**: `build_app()` mounts only `/v1/run`, `/health`, `/readyz` — missing `/metrics`.

**Impact**: The chart probes `/health` (not `/metrics`), so pods will start fine — but operators expecting Prometheus scrape coverage of specialists will see no metrics for them. Spans/traces via OTLP push still work.

**Fix needed (optional)**: add a `prometheus_client` `generate_latest()` route to `build_app()` matching the tool_base pattern.

---

## Cross-check results — all clean

### C1. Image references vs. buildable images

Rendered image list cross-referenced against the build-images.yml + release.yml matrices:

| Source                                          | Verdict |
|-------------------------------------------------|---------|
| `neoncart`, `supportbot`, `llm-gateway`         | OK (app-images matrix) |
| `migrate`, `seed`                               | OK (app-images matrix) |
| `nc-chatbot`, `nc-fraud-detector`, `nc-fulfillment-orchestrator` | OK |
| `sb-router` ... `sb-escalator` (11 specialists) | OK |
| All 16 tool images (snake_case names)           | OK after F2 fix |
| `postgres:16-alpine`                            | OK (upstream) |
| `otel/opentelemetry-collector-contrib:0.96.0`   | OK (upstream) |
| `grafana/k6:0.50.0`                             | OK (upstream, disabled in deploy) |
| `busybox:1.36` (helm test pod)                  | OK (upstream) |

### C2. Service-name DNS resolution

Every hostname referenced in env vars has a matching Service:

| env-var hostname            | Service file                                 | Resolves? |
|-----------------------------|----------------------------------------------|-----------|
| `postgres`                  | `templates/postgres/service.yaml`            | yes       |
| `llm-gateway`               | `templates/llm-gateway/service.yaml`         | yes       |
| `otel-collector`            | `templates/otel-collector/service.yaml`      | yes       |
| `neoncart`                  | `templates/neoncart/service.yaml`            | yes       |
| `supportbot`                | `templates/supportbot/service.yaml`          | yes       |
| `nc-chatbot` (hardcoded in src)  | `templates/specialists/loop.yaml`       | yes       |
| `sb-router` (chart env)     | `templates/specialists/loop.yaml`            | yes       |
| `search-products`, `kb-search`, … 16 tool services | `templates/tools/loop.yaml` | yes (after F1+F2) |

Specialist `call_tool()` builds URLs as `http://{name.replace('_', '-')}/v1/invoke` — matches the hyphen Service names emitted by `tools/loop.yaml`. Verified.

### C3. ConfigMap / Secret references

All four secretKeyRef + three configMapKeyRef names have a matching template defining them:

| Referenced name             | Defined in                                   |
|-----------------------------|----------------------------------------------|
| `postgres-creds` (DATABASE_URL, DATABASE_URL_SYNC, POSTGRES_PASSWORD) | `templates/postgres/secret.yaml` |
| `llm-gateway-creds`         | `templates/llm-gateway/secret.yaml`          |
| `otel-grafanacloud-creds`   | `templates/otel-collector/secret.yaml`       |
| `neoncart-branding`         | `templates/neoncart/configmap.yaml`          |
| `supportbot-branding`       | `templates/supportbot/configmap.yaml`        |
| `llm-gateway-config`        | `templates/llm-gateway/configmap.yaml`       |
| `otel-collector-config`     | `templates/otel-collector/configmap.yaml`    |

Both `DATABASE_URL` (asyncpg) and `DATABASE_URL_SYNC` (psycopg2) keys exist in the postgres-creds secret — the parallel async/sync-driver fix has landed.

### C4. Volume mounts vs. volumes

Every `volumeMounts` has a matching pod-level `volumes` entry:

| Pod                     | Mount → Volume                                     |
|-------------------------|----------------------------------------------------|
| `llm-gateway`           | `config` → ConfigMap `llm-gateway-config`          |
| `otel-collector`        | `config` → ConfigMap `otel-collector-config`       |
| `postgres`              | `postgres-data` → volumeClaimTemplate              |
| `k6` (disabled)         | `scripts` → ConfigMap `k6-scenarios`               |

No dangling mounts.

### C5. Probe paths vs. app routes

| App                          | `/health` | `/readyz` | `/metrics` |
|------------------------------|-----------|-----------|------------|
| `src/neoncart/app/main.py`   | yes       | yes       | yes        |
| `src/supportbot/app/main.py` | yes       | yes       | yes        |
| `src/llm-gateway/app/main.py`| yes       | yes       | yes        |
| `src/tools/_base/.../main.py`| yes       | yes       | yes        |
| `src/specialists/_base/.../main.py` | yes | yes      | **missing** (F6) |

Chart only probes `/health`, so the missing `/metrics` on specialists does not fail deploy — but it's worth filing if anyone hooks up Prometheus scraping later.

### C6. OTel collector config

- OTLP HTTP exporter endpoint: `https://otlp-gateway-prod-us-east-0.grafana.net/otlp` — correct format
- Authorization: `Basic <b64(instanceId:apiToken)>` — correct format (`MTM3MjE3ODpnbGNf...` decodes to `1372178:glc_...`)
- Pipelines: traces, metrics, logs — all three present with `memory_limiter`, `resourcedetection/env`, `batch` processors + the `otlphttp/grafanacloud` exporter
- No missing processor references; `health_check` extension wired to `service.extensions`
- `otel-collector-config` ConfigMap baked at template-time so credentials end up in plaintext inside the ConfigMap — security smell but not a deploy-breaker. The Secret `otel-grafanacloud-creds` is created and bound as env vars on the Deployment but never read by the collector config — dead refs, harmless.

### C7. Specialists / tools loops

- `_` → `-` sanitization for DNS names: correct in both loops (`$dnsName := $name | replace "_" "-"`)
- Each loop iteration emits one Deployment + one Service: confirmed (33 specialist resources + 32 tool resources from 14 specialists + 16 tools)
- Service names are reachable via `http://<dnsName>` from any pod in the namespace: confirmed by cross-checking against `specialist.call_tool()` URL pattern

### C8. Specialist `call_tool()` URL pattern

`http://{tool_name.replace('_', '-')}/v1/invoke` matches the `$dnsName` Service names in `tools/loop.yaml`. Verified for every `tool_allowlist` entry across all 14 specialists.

### C9. Seed + migrate Job ordering

- `migrate` Job: `helm.sh/hook-weight: "1"` → runs first
- `seed` Job: `helm.sh/hook-weight: "2"` → runs after migrate
- Both reference `DATABASE_URL_SYNC` (psycopg2) from `postgres-creds`. Async URL is used by the FastAPI apps + tools — all correct.
- After F3 fix, migrate Job waits for Postgres readiness before running `alembic upgrade head`.

### C10. Postgres readiness probe

Probe: `pg_isready -U postgres -d observibelity`. The `-d` flag forces a real connection to the named database, which only succeeds once `initdb` has finished AND the `POSTGRES_DB` env-var-driven database creation has run. This means the Service won't add the pod to its endpoints until the DB is genuinely usable — exactly what migrate needs.

`initialDelaySeconds: 5`, `periodSeconds: 10`, `failureThreshold: 6` → up to 65s of bootstrap tolerance before marking unready. Sufficient for postgres:16-alpine on a typical k3s node.

---

## Deployment-readiness checklist

- [x] `helm template observibelity /workspace/observibelity -f values-deploy.yaml --namespace observibelity` renders cleanly (4818 lines, 81 YAML docs, parses with `yaml.safe_load_all`)
- [x] 34 Deployments, 35 Services, 1 StatefulSet, 2 Jobs, 3 Secrets, 4 ConfigMaps emitted
- [x] All image references map to buildable images
- [x] All Service references resolve to a Service definition
- [x] All Secret/ConfigMap references map to a template-defined resource
- [x] Migrate Job will wait for Postgres before running alembic

## Next-deploy expectations

With the three BLOCKER/HIGH fixes (F1, F2, F3) applied:

1. Tools will actually deploy this round (previously: zero tool pods).
2. Tool pods will pull the right images from GHCR (previously: ImagePullBackOff).
3. Migrate Job will not flap on first install while Postgres bootstraps.

Three flagged-for-user items (F4 model env var, F5 specialist allowlist env var, F6 specialist `/metrics`) are config / observability quality issues, not pod-failure bugs. They can wait for a Python-source PR after this deploy is green.
