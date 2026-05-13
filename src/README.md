# src/ — application code

This directory holds Phase 1+ application code. Each subdirectory is a pod that runs in the cluster.

## Layout

```
src/
├── neoncart/         FastAPI app: e-commerce frontend + chatbot widget
├── supportbot/       FastAPI app: "Ask Acme" internal support bot (Phase 2)
├── llm-gateway/      FastAPI: centralized LLM routing
├── specialists/      sub-agent pods (chatbot, fraud, fulfillment, …)
└── tools/            shared microservices (search_products, kb_search, place_order, …)
```

## Conventions

- Each subdirectory has its own `Dockerfile`, `pyproject.toml`, `README.md`, and `tests/`
- All apps use **FastAPI + Pydantic 2 + uvicorn**
- All apps use **OpenTelemetry SDK** with auto-instrumentation (`opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-asyncpg`)
- All apps emit logs to stdout as JSON; OTel collector ingests
- Naming: `nc-<name>` for NeonCart specialists, `sb-<name>` for Support Bot specialists
- Tool naming: `<verb>_<noun>` (snake_case) → matches the planner

## Phase 1 vs Phase 2

Phase 1 ships:
- `src/neoncart/`
- `src/llm-gateway/`
- `src/specialists/{nc-chatbot,nc-fraud-detector,nc-fulfillment-orchestrator}/`
- `src/tools/{search_products,get_product,get_order_history,geo_lookup,get_inventory,place_order}/`

Phase 2 adds: Support Bot, remaining specialists, remaining tools.

## See also
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — system topology
- [docs/PROVIDERS.md](../docs/PROVIDERS.md) — LLM provider plugin model
- [Live planner § 01–04](https://claude.wombatwags.com/planner/ai-o11y/) — full spec
