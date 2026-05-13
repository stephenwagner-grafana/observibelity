# Mice-RCA Validation Report

Date: 2026-05-13
Cluster: k3s `observibelity` namespace
Grafana Cloud stack: `stephenwagner.grafana.net`

## TL;DR

| Path | Triggers `rodent_qty` 42703 error? | Surfaces in Tempo? |
|------|-----------------------------------|--------------------|
| **A — Direct tool call** (`curl get-inventory` with `X-Caller`) | YES | YES (with full error msg in span status) |
| **B — Edit system prompt + rebuild** | NOT NEEDED | n/a |
| **C — Chat UI → nc-chatbot** | NO (chatbot has no `get_inventory` in `TOOL_ALLOWLIST`; calls `place_order` / `get_product` instead) | n/a |
| **C' — Direct hit on nc-fulfillment-orchestrator** (the *actual* mice-RCA path in code) | NO — blocked by 403 (real bug, see below) | YES (orchestrator span errors, but classified `tool_unavailable` not `database_schema`) |

Path A satisfies the exit criteria; the artificial error, full Postgres traceback, and `rodent_qty does not exist` message are all visible in Tempo spans. **However**, the natural chatbot-driven narrative is broken by a header-propagation bug in `specialist_base.specialist.call_tool`.

## Path A — Direct tool call

Five requests were sent against `svc/get-inventory` with `X-Caller: nc-fulfillment-orchestrator` and SKUs `mice-001`, `mice-002`, `rodent-007`, `mice-003`, `mice-rca-test`. All returned HTTP 500 with body:

```json
{"detail":"(sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) <class 'asyncpg.exceptions.UndefinedColumnError'>: column \"rodent_qty\" does not exist\n[SQL: SELECT rodent_qty FROM catalog_items WHERE sku = $1]\n[parameters: ('mice-001',)]\n(Background on this error at: https://sqlalche.me/e/20/f405)"}
```

Pod `get-inventory-687b8c7967-s4dwk` logged each as `POST /v1/invoke HTTP/1.1 500 Internal Server Error`.

## Traces in Tempo

TraceQL queries returned the expected traces:

- `{ resource.service.name = "get_inventory" && status = error }` — 7+ traces
- `{ .ai_o11y.usecase = "mice-rca" }` — covers orchestrator + neoncart + tool spans

### Representative trace (Path A direct call): `711bc31ef03c48f24ed255eb75418454`

Spans:
- `POST /v1/invoke` — `STATUS_CODE_ERROR`, `http.status_code=500`
- `tool.get_inventory` — `STATUS_CODE_ERROR` with full status message:
  > `ProgrammingError: (sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) <class 'asyncpg.exceptions.UndefinedColumnError'>: column "rodent_qty" does not exist [SQL: SELECT rodent_qty FROM catalog_items WHERE sku = $1] [parameters: ('mice-rca-test',)]`
- `error=true` attribute set

### Direct Tempo deeplinks

- Single trace view: <https://stephenwagner.grafana.net/explore?left=%7B%22datasource%22%3A%22grafanacloud-traces%22%2C%22queries%22%3A%5B%7B%22query%22%3A%22711bc31ef03c48f24ed255eb75418454%22%2C%22queryType%22%3A%22traceql%22%2C%22refId%22%3A%22A%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%22now-1h%22%2C%22to%22%3A%22now%22%7D%7D>
- All `get_inventory` errors: <https://stephenwagner.grafana.net/explore?left=%7B%22datasource%22%3A%22grafanacloud-traces%22%2C%22queries%22%3A%5B%7B%22query%22%3A%22%7B+resource.service.name+%3D+%5C%22get_inventory%5C%22+%5Cu0026%5Cu0026+status+%3D+error+%7D%22%2C%22queryType%22%3A%22traceql%22%2C%22refId%22%3A%22A%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%22now-1h%22%2C%22to%22%3A%22now%22%7D%7D>
- All mice-rca error traces: <https://stephenwagner.grafana.net/explore?left=%7B%22datasource%22%3A%22grafanacloud-traces%22%2C%22queries%22%3A%5B%7B%22query%22%3A%22%7B+.ai_o11y.usecase+%3D+%5C%22mice-rca%5C%22+%5Cu0026%5Cu0026+status+%3D+error+%7D%22%2C%22queryType%22%3A%22traceql%22%2C%22refId%22%3A%22A%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%22now-1h%22%2C%22to%22%3A%22now%22%7D%7D>

## Path C / C' — Chat-driven flows (NOT producing the canonical error)

### C — `POST /chat` on `svc/neoncart`

Three requests were sent referencing SKU `mice-001` / `mice-007` / `mice-099` (e.g. "place an order for a pet mouse, the SKU is mice-001"). All returned `Chatbot error 500`. The pod log shows the chatbot **did** make tool calls but to `place_order` (422) and `get_product` (500). Specifically, `nc-chatbot.TOOL_ALLOWLIST = [search_products, get_product, get_order_history, place_order]` — `get_inventory` is **not** in the allowlist. So even if the LLM produced a `mice-*` SKU, it would never reach the artificial-error tool from this specialist.

### C' — Direct `POST /v1/run` on `svc/nc-fulfillment-orchestrator`

This is the canonical mice-RCA path. The orchestrator has a `_RODENT_PATTERN` regex and proactively probes `get_inventory` when the request looks rodent-shaped (see `src/specialists/nc-fulfillment-orchestrator/app/specialist.py` lines 26-29, 67-92). When invoked with rodent SKUs the orchestrator hit `get_inventory` — but the request was rejected with **403 Forbidden** instead of producing the `rodent_qty` error. The trace `7ed74b949c43d867eb22332afe199f5e` confirms:

- `tool.get_inventory` span status: `Client error '403 Forbidden' for url 'http://get-inventory/v1/invoke'`
- Parent span `specialist.nc-fulfillment-orchestrator.fulfill` gets `ai_o11y.error.kind=tool_unavailable` (because the orchestrator's `_record_inventory_error` only sets `database_schema` when the detail contains `rodent_qty` or `column`)

### Root cause (real bug, blocks the demo narrative)

`specialist_base.specialist.call_tool` (file `src/specialists/_base/specialist_base/specialist.py`, lines 106-128) does NOT forward an `X-Caller` header when POSTing to the tool. `get_inventory`'s `ALLOWED_CALLERS = ["nc-fulfillment-orchestrator", "nc-chatbot"]` therefore rejects every specialist-to-tool call as `caller=None` → 403. The artificial error path is unreachable from any specialist as long as this is the case.

```python
# specialist.py:126 — missing the X-Caller header
resp = await self.client.post(tool_url, json=args)
```

Should be:

```python
resp = await self.client.post(tool_url, json=args, headers={"X-Caller": self.NAME})
```

## Recommendations

1. **Fix the header bug** in `specialist_base.specialist.call_tool` to forward `X-Caller: <specialist.NAME>`. Without this the entire `ALLOWED_CALLERS` allowlist is non-functional, and the canonical mice-RCA narrative (orchestrator → tool → schema error) never fires.
2. **System prompt does NOT need adjusting on nc-chatbot.** The canonical mice-RCA flow is `nc-fulfillment-orchestrator` (which has the regex + proactive probe in code). Once the header bug above is fixed, the narrative will work end-to-end without prompt-engineering tricks.
3. Optionally, add `get_inventory` to `nc-chatbot.TOOL_ALLOWLIST` so the chat UI can also surface the bug — but this isn't required; the orchestrator path is sufficient and architecturally cleaner.

## Files referenced

- `/workspace/observibelity/src/tools/get_inventory/app/tool.py` (artificial error implementation)
- `/workspace/observibelity/src/specialists/nc-fulfillment-orchestrator/app/specialist.py` (canonical RCA path, regex + probe)
- `/workspace/observibelity/src/specialists/nc-chatbot/app/specialist.py` (chat UI specialist — does NOT reach `get_inventory`)
- `/workspace/observibelity/src/specialists/_base/specialist_base/specialist.py` (header bug location, lines 106-128)
- `/workspace/observibelity/src/tools/_base/tool_base/tool.py` (`authorize` check, lines 80-84)
- `/workspace/observibelity/src/tools/_base/tool_base/main.py` (HTTP handler reads `X-Caller` header)
