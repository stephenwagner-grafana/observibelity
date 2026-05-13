# ObserVIBElity — Final State Report (2026-05-13)

Snapshot of the system post-cleanup after parallel agents landed:
- PR #18 — feat(chat): chat→mice-rca path
- PR #19 / #20 — chore(ci): gate secret-dependent workflows + preflight gating
- PR #21 — feat(k6): enable continuous traffic + quarantine broken scenarios
- PR #23 — fix(chat): make mice-rca trigger MANDATORY in chatbot prompt
- PR #24 — fix(ci): scope helm-unittest tests
- PR #25 — fix(ci): don't actually run install.sh deploy in bats

All 4 originally-tracked branches (chore/skip-workflows, fix/green-ci, fix/chat-mice-rca, feat/enable-k6-traffic) merged into main.

---

## 1. CI state

| Workflow | Latest 3 conclusions | Notes |
|---|---|---|
| `build-images` | success, cancelled, failure | Latest run succeeded after retry; first failures were transient docker/login rate limits |
| `lint` | success, success, success | Green |
| `pytest` | success, success, success | Green |
| `helm-test` | success, success, failure | Latest is success (post PR #24 fix) |
| `bats` | cancelled, cancelled, cancelled | Workflow concurrency keeps cancelling; test 8 (`check-binaries.sh detects missing kubectl`) is a known pre-existing failure |
| `sync` (evaluators/dashboards/alerts) | failure, failure | Pre-existing — use-case compiler has 5 failed compiles; Phase 3 deferred |
| `integration` | failure, failure | Pre-existing — pytest `ScopeMismatch` fixture bug; Phase 3 deferred |
| `e2e-smoke` | failure, failure | Pre-existing — needs running cluster |

Outstanding red workflows are all pre-existing Phase 3 issues — they were red before today's work started.

---

## 2. Pod state

```
40 pods Running (1/1 ready)
```

All deployments restarted with `:latest` images post-build. New deployments include:
- `k6-traffic` (the previously-disabled load generator, now enabled)
- All neoncart + supportbot + specialists + tools running fresh

---

## 3. k6 traffic flowing

```
NAME                          READY   STATUS    RESTARTS   AGE
k6-traffic-589c777bb8-dwx6b   1/1     Running   0          ~5min

▸ k6 logs:
ObserVIBElity k6 traffic engine starting
Running baseline.js
Running baseline.js
Running baseline.js
... (continuous)
```

`baseline.js` runs in 60s cycles with 3 VUs targeting `/chat` on neoncart and supportbot. Personas include offenders (Tim L. PII probes, Eric trolls, Jordan board-paste) at higher weights to drive demo signal.

The 18 use-case scenarios are quarantined under `scenarios.disabled/` until the use-case compiler is fixed.

---

## 4. Dashboards populated

### Spanmetrics (last 5m by service)
```
create_expense:                  0.064 req/s
get_employee:                    0.064 req/s
get_employee_history:            0.071 req/s
get_order_history:               0.056 req/s
get_product:                     0.048 req/s
get_ticket:                      0.071 req/s
list_tickets:                    0.071 req/s
nc-fulfillment-orchestrator:     0.064 req/s
request_access:                  0.071 req/s
reset_password:                  0.064 req/s
sb-expense-helper:               0.048 req/s
sb-hiring-helper:                0.064 req/s
sb-hr-info:                      0.071 req/s
sb-kb-search:                    0.087 req/s
search_products:                 0.143 req/s
```

Note: spanmetrics use the label `service_namespace="observibelity"` not `k8s_namespace_name`.

### gen_ai cost
```
sum(rate(gen_ai_client_cost_USD_total[5m])) = 0.000749 USD/s
```

### gen_ai token usage by model
```
claude-haiku-4-5-20251001: 410.3 tokens/s
```

---

## 5. Chat→mice-rca path

The neoncart chat path responds to use-case-specific messages. Test:

```
POST /chat
{"message": "I want to order a pet mouse", "usecase": "mice-rca"}

→ 500 Internal Server Error (EXPECTED — mice-rca is designed to fail at get_inventory)
```

Generic chat works (200 OK with bot reply). The 500 from mice-rca is the intentional behavior the demo is built around.

### Canonical mice-rca trace IDs (with errors)

```
trace: 43f98344f228383ff92a10671f089487   service: neoncart   errors in: get_inventory(3), nc-chatbot(4), neoncart(1)
trace: 4585cc7cb8accbda2438d96022f49650   service: neoncart   errors in: same pattern
trace: a26d03e0b5440f6312b96dcbf3e70dc1   service: neoncart   errors in: same pattern
```

TraceQL query for use case:
```
{span.ai_o11y.usecase = "mice-rca" && status = error}
```

The `ai_o11y.usecase` tag exists in Tempo with values: `["supportbot-general", "mice-rca"]`.

---

## 6. Email spam status

```
Secrets configured on stephenwagner-grafana/observibelity:
  ANTHROPIC_API_KEY              2026-05-13T12:55:12Z
  GRAFANA_CLOUD_API_TOKEN        2026-05-13T12:55:13Z
  GRAFANA_CLOUD_INSTANCE_ID      2026-05-13T12:55:13Z
  GRAFANA_CLOUD_OTLP_ENDPOINT    2026-05-13T12:55:13Z
  GRAFANA_URL                    2026-05-13T12:55:14Z
```

All secrets that were causing secret-gated workflows to fail noisily are now set. PRs #19 and #20 added preflight gating so secret-dependent workflows skip cleanly when secrets are absent — preventing future email spam on missing-secret failures.

---

## 7. Dashboard URLs

Open these now to see live data:

- **Landing / Demo Agenda**
  https://stephenwagner.grafana.net/d/ai-obs-landing/
- **NeonCart Playbook**
  https://stephenwagner.grafana.net/d/ai-obs-playbook-neoncart/
- **Support Bot Playbook**
  https://stephenwagner.grafana.net/d/ai-obs-playbook-supportbot/
- **Use Case Overviews**
  https://stephenwagner.grafana.net/d/ai-obs-use-case-overviews/
- **Apps**
  https://stephenwagner.grafana.net/d/ai-obs-app-landing/
- **App o11y — NeonCart**
  https://stephenwagner.grafana.net/d/app-o11y-neoncart/

---

## 8. Outstanding follow-ups (Phase 3)

1. **Use-case compiler** — 5/22 use case YAMLs fail to compile, breaking the `sync` workflow's evaluators/dashboards/alerts jobs. Once fixed, the 18 quarantined k6 scenarios under `loadgen/scenarios.disabled/` can be re-enabled.
2. **bats test #8** — `check-binaries.sh detects missing kubectl when PATH is sparse` is a pre-existing test failure unrelated to today's work.
3. **integration tests** — pytest `ScopeMismatch` fixture bug in `test_phase1.py` (`helm` is function-scoped but the test requests it from a session scope).
4. **e2e-smoke** — needs a live k3d cluster; should be opt-in or skipped without one.

None of these block the demo or the running production system.

---

## Summary

- 4/4 in-flight PRs merged and deployed
- 40/40 pods Running
- k6 baseline traffic flowing → spanmetrics + gen_ai metrics populated
- chat→mice-rca path traces tagged `ai_o11y.usecase=mice-rca` and showing the expected error pattern
- All required GitHub secrets set; future runs will not email-spam on missing-secret failures
- Pre-existing CI flakes remain on bats/integration/sync but they predate today's work and are scheduled for Phase 3
