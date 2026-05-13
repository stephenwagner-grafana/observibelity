# tools/ — shared microservices

Tools are **shared microservices**, not cloned per specialist. One tool pod per (tool, app); many specialists call it.

## Phase 1 tools

| name | role | backing tables |
|---|---|---|
| search_products | full-text + filter search | catalog_items, categories |
| get_product | fetch product details by ID | catalog_items, brands, promotions |
| get_order_history | list orders for a persona | orders, order_items, personas |
| geo_lookup | resolve IP/zip → country/state | ip_geo, countries |
| get_inventory | check stock for a SKU | catalog_items (stock_qty column) |
| place_order | create order + decrement stock | orders, order_items, catalog_items |

## Phase 2 adds 15 more tools
- 5 more NeonCart tools (cancel_order, apply_promo, calculate_shipping, etc.)
- 10 Support Bot tools (kb_search, list_tickets, get_employee, etc.)

## Tool contract

Each tool subclasses the `Tool` base (in `src/tools/_base/`) with:

```python
class SearchProductsArgs(BaseModel):
    query: str
    limit: int = 20

class SearchProductsResult(BaseModel):
    items: list[ProductRef]
    total: int

class SearchProducts(Tool):
    Args = SearchProductsArgs
    Result = SearchProductsResult
    
    # 13 customization knobs (see Live planner § 04 Tools):
    side_effect = False
    idempotent = True
    timeout_sec = 5
    max_concurrency = 50
    cache_ttl_sec = 60
    retries = 2
    allowed_callers = ["nc-chatbot", "nc-recommender"]
    backing_tables = ["catalog_items", "categories"]
    requires_secrets = []
    replicas = 2
    
    async def execute(self, args: SearchProductsArgs) -> SearchProductsResult:
        ...
```

The base class handles OTel spans, FastAPI route, Pydantic validation, Prometheus metrics, Loki logs, in-pod LRU cache, concurrency semaphore.

## Adding a new tool

1. Create `src/tools/<verb>_<noun>/` with main.py, Dockerfile, pyproject.toml, tests/
2. Subclass `Tool`, fill in Args/Result, set knobs
3. Add to `registry/tools.yaml`
4. Add to specialists' `tool_allowlist` for any specialist that should call it
5. Build + deploy: `make images TOOL=<name>` then `make dev`

See [Live planner § 04 Tools](https://claude.wombatwags.com/planner/ai-o11y/#tools).
