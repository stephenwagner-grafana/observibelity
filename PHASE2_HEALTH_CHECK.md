# ObserVIBElity Phase 2 — Running-Pod Health Check

**Date:** 2026-05-13
**Cluster:** k3s, 4 nodes (fourth-mate NotReady)
**Namespace:** `observibelity`
**Scope:** Verify the 5 pods in `Running` phase are actually functional, not just up.

---

## TL;DR

| Pod              | Status              | Verdict                                    |
|------------------|---------------------|--------------------------------------------|
| postgres-0       | Running 1/1         | **HEALTHY** — schema at rev 0007, fully seeded |
| llm-gateway      | Running 1/1         | **HEALTHY** — end-to-end Anthropic call returns content + cost |
| otel-collector   | Running 1/1         | **HEALTHY** — pipeline "Everything is ready", no export errors |
| neoncart         | Running 1/1         | **RUNNING-BUT-BROKEN** — every HTML route 500s (starlette 1.0 signature change) |
| supportbot       | Running 1/1         | **RUNNING-BUT-BROKEN** — same template bug + Persona model out of sync with personas schema |

**Mice-RCA demo go/no-go:** **NO-GO** as currently shipped, even if all 32 specialists come back online. The two user-facing apps cannot render their UIs and supportbot has a schema mismatch on the personas table. Both issues are application-code bugs that need image/code fixes; specialists healing won't unblock them.

---

## 1. postgres-0 — HEALTHY

| Check | Result |
|---|---|
| Version | PostgreSQL 16.13 on x86_64-pc-linux-musl |
| `\dt` | 19 tables present including `personas`, `catalog_items`, `neoncart_kb`, `supportbot_kb`, `tickets` |
| `alembic_version` | **0007** (after parallel agent re-ran migrate; was 0006 at first check) |
| `count(personas)` | **200** |
| `count(catalog_items)` | **518** |
| `count(neoncart_kb)` | **20** |
| `count(apps)` | 0 (table exists, unseeded — likely expected) |
| `count(supportbot_kb)` | (table exists; row count not checked, but tabe is created by migration 0007) |

**Notes:**
- Initial state had `alembic_version = 0006` and missing `supportbot_kb` table. The parallel agent appears to have re-run the migrate job which advanced schema to 0007 and re-ran the seed job (which is now `Complete`, previously `Failed`).
- Schema/model mismatch: `personas` table has columns `id, persona_id, name, email, role, archetype, offender_pattern, weight, created_at`. The **supportbot** app's `Persona` model includes a `department` column (models.py L37) that does NOT exist in the DB. This causes `/api/personas` to 500 (see supportbot section).

---

## 2. llm-gateway — HEALTHY

| Check | Result |
|---|---|
| `/health` | `200 OK` body `ok` |
| `/readyz` | `200 OK` `{"providers":{"anthropic":true,"ollama":false}}` |
| `/metrics` | Prometheus metrics served (Python GC, process, exposition) |
| `POST /v1/complete` | `200 OK` — content `"pong"`, usage tokens populated, cost in USD, `provider=anthropic`, `model=claude-haiku-4-5-20251001` |
| Pod log of test call | `INFO:httpx:HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"` + structured-JSON log line with `gen_ai.*` attributes |

**Verdict:** Fully functional. Real upstream Anthropic call works, cost accounting is wired, structured logs carry the OTel attribute names the dashboards expect (`gen_ai.system`, `gen_ai.usage.cost.total_usd`, `ai_o11y.usecase`, etc.). The `ollama` provider is `false` — that is expected since Ollama is opt-in and the demo defaults to cloud.

---

## 3. otel-collector — HEALTHY

| Check | Result |
|---|---|
| Logs (full file) | Receivers OTLP gRPC :4317 and HTTP :4318 started; health_check :13133 ready; "Everything is ready. Begin running and processing data." at startup |
| Errors / "failed to send" / auth failures | **None found in the last 200 log lines** |
| Health endpoint (in-pod) | `200 OK` |
| Configured exporter | `otlphttp/grafanacloud` → `https://otlp-gateway-prod-us-east-0.grafana.net/otlp` with Basic auth header (Grafana Cloud creds embedded in configmap `otel-collector-config`) |
| Receivers | OTLP gRPC + HTTP |
| Processors | `memory_limiter` (80% / 25% spike on 3 GiB), `batch` (8192/5s), `resourcedetection/env` |

**Verdict:** Pipeline up, no auth issues against Grafana Cloud OTLP gateway. Cannot prove successful export count without `otelcol_exporter_sent_*` self-metrics (port-forward to :8888 returned no metrics in my brief test — likely no traffic yet because specialists are down). No-error baseline strongly suggests the exporter would work as soon as it receives spans.

**Security note (not a health issue):** The Grafana Cloud Basic-auth token is in the configmap in plaintext base64. Consider migrating to a secret in a follow-up.

---

## 4. neoncart — RUNNING-BUT-BROKEN

| Check | Result |
|---|---|
| `/health` | `200 OK` `ok` |
| `/readyz` | `200 OK` `{"postgres":true}` |
| `/metrics` | `200 OK` |
| `/api/personas` | `200 OK`, returns **200** persona objects (jq length = 200) |
| `/` (root HTML page) | **500 Internal Server Error** |
| `/catalog` | **500** |
| `/cart` | **500** |
| `/products/{id}` | **500** |
| `POST /chat` with valid string `persona_id` | `503 Service Unavailable` with body `Chatbot unreachable: All connection attempts failed` — **graceful** (as the task spec required) |
| `POST /chat` with invalid (int) `persona_id` | `422 Unprocessable Entity` — validation works |

### Root cause for the 500s — starlette TemplateResponse signature change

The installed starlette is **1.0.0**, whose `TemplateResponse` signature is:

```
TemplateResponse(self, request, name, context=None, status_code=200, ...)
```

But `app/main.py:128` calls it positionally as:

```python
return templates.TemplateResponse(template_name, ctx)
```

So starlette treats `template_name` (a string) as the **request** object and `ctx` (a dict) as the **template name**. Inside `get_template(name)`, Jinja2's environment cache then does `self.cache.get(cache_key)` against a dict, blowing up with `TypeError: unhashable type: 'dict'`.

Every HTML route in neoncart goes through `_render_with_personas(...)` and is affected. Pure JSON APIs (`/health`, `/readyz`, `/api/personas`, `/metrics`) bypass templating and work fine.

**Fix needed:** either pin starlette to a pre-1.0 release in the neoncart image's pyproject, or update all four+ `TemplateResponse(...)` call sites to pass `request` as the first positional arg.

---

## 5. supportbot — RUNNING-BUT-BROKEN

| Check | Result |
|---|---|
| `/health` | `200 OK` `ok` |
| `/readyz` | `200 OK` `{"postgres":true}` |
| `/metrics` | `200 OK` |
| `/` (root HTML page) | **500** — same starlette 1.0 TemplateResponse signature bug (4 call sites at lines 144, 162, 178, 195 in `/app/app/main.py`) |
| `/tickets` | **500** (template route) |
| `/api/personas` | **500** — `sqlalchemy.exc.ProgrammingError: ... column personas.department does not exist` |
| `POST /chat` with valid string `persona_id` | `503` with body `Support bot unreachable: All connection attempts failed` — **graceful** |
| `POST /chat` with invalid (int) `persona_id` | `422` — validation works |

### Root causes

1. **Same starlette 1.0 TemplateResponse signature change** as neoncart. All HTML routes are broken.
2. **Persona model is out of sync with the personas schema.** `app/models.py:37` declares `department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)`. The DB schema for `personas` from migration `0001_initial` does NOT include a `department` column. Either:
   - the model was updated and a migration to add `department` was forgotten, or
   - the model is wrong and should be reverted.

This means **`/api/personas` 500s indefinitely** even once specialists are healthy, breaking any UI flow that lists personas in the support-bot app.

---

## otel-collector errors observed

None. No `error`, `failed`, `denied`, `unauthorized`, `401`, `403`, or `reject` matches in 200 lines of logs. Grafana Cloud OTLP creds appear correct (no auth rejections).

---

## Mice-RCA demo go/no-go

Assuming the parallel agent fixes all 32 CrashLoopBackOff specialists / tools, here is what **still** would not work:

- **neoncart UI** — root, catalog, cart, product detail pages all 500. The "mice" can't even see the home page.
- **supportbot UI** — same root/tickets/everything 500.
- **supportbot /api/personas** — 500s from schema mismatch, so the persona picker likely won't populate.
- **neoncart /api/personas** — works (200 personas), so neoncart's persona picker would populate if the page rendered… which it doesn't.
- **POST /chat on both apps** — already returns graceful `503 Chatbot/Support bot unreachable` when downstream is down, so when nc-chatbot / sb-router come up healthy this should immediately start working **as an API**, but you can only reach it from the broken HTML pages.

### Required fixes before demo
1. Pin starlette to `<1.0` in the neoncart and supportbot images, OR update all `TemplateResponse(...)` call sites to pass `request` first.
2. Add a migration creating `personas.department` (and any other newly-modeled columns), or remove `department` from the `Persona` model in supportbot. Re-run migrate + seed.

Both are image/code-level changes — not Helm/k8s — so they require a rebuild + push of `observibelity-neoncart` and `observibelity-supportbot` (and, in case 2, a new migration).

---

## Evidence — selected raw output

```
$ curl -sS http://localhost:8001/v1/complete -X POST ... 
{"content":"pong","tool_calls":[],"finish_reason":"stop",
 "usage":{"input_tokens":15,"output_tokens":5,
          "cost_usd":{"total_usd":3.9999999999999996e-05}},
 "provider":"anthropic","model":"claude-haiku-4-5-20251001"}
```

```
$ curl -sS http://localhost:8080/  →  500 + log:
  File "/app/app/main.py", line 128, in _render_with_personas
    return templates.TemplateResponse(template_name, ctx)
  ...
TypeError: unhashable type: 'dict'
```

```
$ curl -sS http://localhost:8082/api/personas  →  500 + log:
sqlalchemy.exc.ProgrammingError: 
  asyncpg.exceptions.UndefinedColumnError: column personas.department does not exist
[SQL: SELECT personas.id, personas.name, personas.email, personas.role,
              personas.department FROM personas LIMIT $1::INTEGER]
```

```
$ curl -sS http://localhost:8001/readyz
{"providers":{"anthropic":true,"ollama":false}}
```

```
otel-collector log:
  service@v0.96.0/service.go:169  Everything is ready. Begin running and processing data.
  (no errors in subsequent 200 log lines)
```
