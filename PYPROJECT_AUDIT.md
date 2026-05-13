# Pyproject Dependency Audit — ObserVIBElity

Audit run: 2026-05-13. Compared every `pyproject.toml` under `src/` against
the actual `import` / `from … import` statements in its source tree.

## Method

1. Read each `pyproject.toml`, extracted `[project.dependencies]` and
   `[project.optional-dependencies]`.
2. Walked all `.py` files in the same package (excluding `tests/`).
3. Used `ast.parse` to extract top-level module imports.
4. Filtered out the stdlib (Python 3.12 baseline) and relative imports.
5. Mapped each remaining import to a PyPI distribution name using common
   conventions (`yaml` → `pyyaml`, `PIL` → `Pillow`, etc.) and the
   opentelemetry sub-package layout (`opentelemetry.trace` →
   `opentelemetry-api`, `opentelemetry.instrumentation.X` →
   `opentelemetry-instrumentation-X`, etc.).
6. Flagged any PyPI package that was imported but not declared (either
   directly or via a renamed alias).

## How Dockerfiles use these pyprojects

Each app's Dockerfile dictates whether its `pyproject.toml` is load-bearing:

| Component | `pip install .` in Dockerfile? | Notes |
| --- | --- | --- |
| `neoncart` | YES (in builder stage) | pyproject deps install directly |
| `supportbot` | YES (in builder stage) | pyproject deps install directly |
| `llm-gateway` | YES (in builder stage) | pyproject deps install directly |
| `specialists/_base` | YES (in base image build) | shared specialist runtime |
| `tools/_base` | YES (in base image build) | shared tool runtime |
| `specialists/<name>` | NO — only `COPY app/` on top of base | inherits base image deps |
| `tools/<name>` | NO — only `COPY app/` on top of base | inherits base image deps |

So per-specialist and per-tool pyprojects only matter for documentation,
local `pip install -e .`, and CI workflows — they do **not** drive the
runtime image's package set. However, we still want them to be correct.

## Findings

### Apps (drive `pip install .` directly — these crash without correct deps)

| File | Was declared | Was imported but missing | Fix |
| --- | --- | --- | --- |
| `src/neoncart/pyproject.toml` | fastapi, uvicorn, jinja2, pydantic, asyncpg, sqlalchemy, httpx, otel-distro, otel-instr-fastapi, otel-instr-asyncpg, otel-instr-httpx, prometheus-client, python-multipart | `opentelemetry-api` (via `from opentelemetry import trace`) | Added `opentelemetry-api>=1.27` |
| `src/supportbot/pyproject.toml` | (same set as neoncart) | `opentelemetry-api` (via `from opentelemetry import trace`) | Added `opentelemetry-api>=1.27` |
| `src/llm-gateway/pyproject.toml` | fastapi, uvicorn, pydantic, httpx, anthropic, otel-api, otel-sdk, otel-exporter-otlp, otel-instr-fastapi, otel-instr-httpx, prometheus-client | none — already complete | none |

`opentelemetry-api` was being satisfied transitively via
`opentelemetry-distro[otlp]`, but the `from opentelemetry import trace`
import deserves a direct declaration so the dep is pinned even if a
future distro release drops it. This avoids surprise drift.

### Base packages (drive `pip install .` in the base image)

| File | Missing | Fix |
| --- | --- | --- |
| `src/specialists/_base/pyproject.toml` | `opentelemetry-api` (used in `main.py`, `specialist.py`) | Added `opentelemetry-api>=1.27` |
| `src/tools/_base/pyproject.toml` | `opentelemetry-api` (used in `tool.py`) | Added `opentelemetry-api>=1.27` |

Same reasoning: declare directly anything we import directly.

### Per-specialist pyprojects (only `observibelity-specialist-base` as direct dep)

These specialists pulled imports beyond what the base contract suggests:

| File | Direct imports beyond the base | Action |
| --- | --- | --- |
| `src/specialists/nc-fraud-detector/pyproject.toml` | `opentelemetry` | Added `opentelemetry-api>=1.27` |
| `src/specialists/nc-fulfillment-orchestrator/pyproject.toml` | `httpx`, `opentelemetry`, `opentelemetry.trace` | Added `httpx>=0.27`, `opentelemetry-api>=1.27` |
| `src/specialists/sb-router/pyproject.toml` | `httpx`, `opentelemetry` | Added `httpx>=0.27`, `opentelemetry-api>=1.27` |

The other eight specialists (`sb-employee-info`, `sb-escalator`,
`sb-expense-helper`, `sb-hiring-helper`, `sb-hr-info`,
`sb-it-troubleshoot`, `sb-kb-search`, `sb-policy-finder`,
`sb-security-handler`, `sb-ticket-helper`, `nc-chatbot`) only import
`specialist_base` and stdlib, so the existing single dep is sufficient.

Note: runtime-wise these specialists already worked because the base
image preinstalls `httpx` and the opentelemetry stack — but `pip install
-e .` workflows would have surfaced `ModuleNotFoundError`. Now they
won't.

### Per-tool pyprojects (only `observibelity-tool-base` as direct dep)

All 16 tool packages have `from pydantic import …` and `from sqlalchemy
import …` lines in `app/tool.py` but only declared
`observibelity-tool-base` as a direct dependency. The base does declare
both, so runtime worked. To make `pip install -e .` clean and to keep
pyproject ↔ imports in sync, every tool pyproject now also declares:

```
"pydantic>=2.9",
"sqlalchemy[asyncio]>=2.0",
```

Tools updated (all 16):
`create_expense`, `create_ticket`, `geo_lookup`, `get_employee`,
`get_employee_history`, `get_inventory`, `get_order_history`,
`get_product`, `get_ticket`, `kb_search`, `list_tickets`, `place_order`,
`request_access`, `reset_password`, `search_products`, `update_ticket`.

## Files modified

```
src/neoncart/pyproject.toml
src/supportbot/pyproject.toml
src/specialists/_base/pyproject.toml
src/specialists/nc-fraud-detector/pyproject.toml
src/specialists/nc-fulfillment-orchestrator/pyproject.toml
src/specialists/sb-router/pyproject.toml
src/tools/_base/pyproject.toml
src/tools/create_expense/pyproject.toml
src/tools/create_ticket/pyproject.toml
src/tools/geo_lookup/pyproject.toml
src/tools/get_employee/pyproject.toml
src/tools/get_employee_history/pyproject.toml
src/tools/get_inventory/pyproject.toml
src/tools/get_order_history/pyproject.toml
src/tools/get_product/pyproject.toml
src/tools/get_ticket/pyproject.toml
src/tools/kb_search/pyproject.toml
src/tools/list_tickets/pyproject.toml
src/tools/place_order/pyproject.toml
src/tools/request_access/pyproject.toml
src/tools/reset_password/pyproject.toml
src/tools/search_products/pyproject.toml
src/tools/update_ticket/pyproject.toml
```

## Files left unchanged (no missing deps detected)

```
src/llm-gateway/pyproject.toml
src/specialists/nc-chatbot/pyproject.toml
src/specialists/sb-employee-info/pyproject.toml
src/specialists/sb-escalator/pyproject.toml
src/specialists/sb-expense-helper/pyproject.toml
src/specialists/sb-hiring-helper/pyproject.toml
src/specialists/sb-hr-info/pyproject.toml
src/specialists/sb-it-troubleshoot/pyproject.toml
src/specialists/sb-kb-search/pyproject.toml
src/specialists/sb-policy-finder/pyproject.toml
src/specialists/sb-security-handler/pyproject.toml
src/specialists/sb-ticket-helper/pyproject.toml
```

## Exit criteria

The audit script re-run after fixes reports:

> "All pyprojects satisfy their imports."

Every pyproject's `dependencies` array now declares every PyPI
distribution corresponding to an `import` / `from … import` statement in
its package source. The next image rebuild should not surface any new
`ModuleNotFoundError` crashes that trace back to a missing pyproject
declaration.
