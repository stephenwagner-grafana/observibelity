# Architecture

## What gets deployed (final state)

```
        ┌───────────────────────────────────────────────────────────┐
        │  User browser                                             │
        └──────────────────────────┬────────────────────────────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Ingress         │
                          └────────┬─────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                                         │
       ┌──────▼──────┐                          ┌───────▼──────┐
       │ NeonCart    │                          │ Support Bot  │   (Phase 2)
       │ (FastAPI +  │                          │ (FastAPI +   │
       │  Jinja +    │                          │  Jinja +     │
       │  HTMX)      │                          │  HTMX)       │
       └──────┬──────┘                          └───────┬──────┘
              │                                         │
              ├──────► nc-* specialists                 ├──► sb-* specialists
              │        (~13 pods)                       │     (~11 pods)
              │                                         │
              └──────┬──────────────────────────────────┘
                     │
              ┌──────▼──────┐                  ┌──────────────┐
              │ Tools       │◄────────────────►│ Postgres     │
              │ (~21 pods,  │                  │ (28 tables,  │
              │  shared)    │                  │  app data +  │
              └──────┬──────┘                  │  KBs only)   │
                     │                         └──────────────┘
              ┌──────▼──────┐
              │ llm-gateway │
              │ (1 pod)     │
              └──┬────────┬─┘
                 │        │
        ┌────────▼┐    ┌──▼─────────┐
        │ Claude  │    │ Ollama     │
        │ API     │    │ (5090 LAN) │
        └─────────┘    └────────────┘

        OTel everywhere ──► OTel collector ──► Grafana Cloud
                                                  ├── Mimir (metrics)
                                                  ├── Loki (logs)
                                                  ├── Tempo (traces)
                                                  ├── Pyroscope (profiles)
                                                  └── Sigil (generations + evals)
```

## Phase 0 vs Phase 1 vs Phase 2

| component | Phase 0 | Phase 1 | Phase 2 |
|---|---|---|---|
| install.sh + preflight + wizard | yes | yes | yes |
| Helm chart skeleton | yes | yes | yes |
| Postgres + Alembic migrations | — | yes | yes |
| llm-gateway (Anthropic only) | — | yes | yes |
| NeonCart (FastAPI + chatbot widget) | — | yes | yes |
| Specialists: nc-chatbot, nc-fraud-detector, nc-fulfillment-orchestrator | — | yes | yes |
| Tools: search_products, get_order_history, geo_lookup, place_order, ... | — | yes | yes |
| Use case: `mice-rca` + 2 evaluators | — | yes | yes |
| OTel collector -> Grafana Cloud | — | yes | yes |
| Dashboard: `ai-obs-app-neoncart` | — | yes | yes |
| Support Bot + 11 specialists + 10 SB tools | — | — | yes |
| Ollama provider plugin | — | — | yes |
| All 10 use cases | — | — | yes |
| All 26 evaluators | — | — | yes |
| 6 SLOs + ~14 alerts | — | — | yes |
| k6 in-cluster traffic engine | — | — | yes |
| All 12 dashboards | — | — | yes |
| `.claude/skills/` (vibe-edit tooling) | partial (diagnose-deploy only) | — | yes (6 skills) |

## OOP base classes
Nine classes form the runtime contract — declarative everywhere except where real network code is required (Provider).

| class | role |
|---|---|
| `App` | a frontend pod (NeonCart, Support Bot) |
| `Specialist` | a sub-agent pod with a tool allowlist (nc-chatbot, sb-policy-finder) |
| `Tool` | a shared microservice pod (search_products, kb_search); Pydantic Args/Result; OTel auto-instrumented |
| `UseCase` | a demo scenario (mice-rca, email-cascade); registers dashboards + alerts |
| `Scenario` | a k6 traffic pattern; ConfigMap-mounted JS |
| `Evaluator` | a Grafana Sigil evaluator definition; git-canonical, manual-applied today |
| `Provider` | LLM adapter (Anthropic, Ollama); the one class that requires real network code |
| `SLO` | a service-level objective with error budget |
| `Alert` | a Prometheus alerting rule wired to an SLO |

`Dataset` is NOT a class — use SQLAlchemy models + Alembic migrations + CSV seeders instead.

## Telemetry naming
- **`gen_ai.*`** — OpenTelemetry GenAI semantic conventions are authoritative. Use them for everything spec'd.
- **`ai_o11y.*`** — project-specific custom attributes (use case label, scenario label, persona id, etc.)
- **`<provider>.*`** — provider-native namespaces for drill-down (e.g., `anthropic.cache_creation_input_tokens`)
- Cost ships as `gen_ai.usage.cost.*` (forward-compatible extension)
- Never say "loadgen", "fake", "synthetic", "simulated" anywhere user-visible. Use `traffic_origin = continuous | interactive`.

## Source of truth
**Git is canonical** for everything declarative. Dashboards and alerts round-trip via `gcx`. Evaluators today are created manually in the Grafana Cloud UI (gcx doesn't support them yet); the spec lives in git and `tools/evaluators-sync.sh` will sync once gcx adds support.

## Read more
- [Live planner](https://claude.wombatwags.com/planner/ai-o11y/) — the full ~240 KB design spec, authoritative reference
- [docs/PROVIDERS.md](PROVIDERS.md) — how LLM providers plug in
- [docs/INSTALL.md](INSTALL.md) — installation flow
