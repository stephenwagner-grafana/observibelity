# observibelity-tool-base

Shared base class + FastAPI mount for ObserVIBElity tool microservices.

See [../README.md](../README.md) for the tool contract. The 13 customization knobs are documented on `tool_base.Tool`.

## Knobs

| knob | type | default | meaning |
|---|---|---|---|
| `NAME` | str | `"unknown-tool"` | tool name (used in OTel span + Prom labels) |
| `SIDE_EFFECT` | bool | `False` | mutates state? if True, retries are blocked unless `IDEMPOTENT` |
| `IDEMPOTENT` | bool | `True` | safe to retry on failure? |
| `TIMEOUT_SEC` | int | `5` | per-invocation timeout |
| `MAX_CONCURRENCY` | int | `50` | semaphore depth |
| `CACHE_TTL_SEC` | int | `0` | in-pod LRU cache TTL; 0 disables |
| `RETRIES` | int | `0` | retries on failure |
| `ALLOWED_CALLERS` | list[str] | `[]` | empty = anyone; otherwise specialist allowlist |
| `REQUIRES_ACL` | bool | `False` | (reserved) per-row ACL check |
| `BACKING_TABLES` | list[str] | `[]` | Postgres tables touched; non-empty enables DB session injection |
| `REQUIRES_SECRETS` | list[str] | `[]` | secret keys expected via env |
| `REPLICAS` | int | `1` | desired k8s replica count (read by Helm) |
| `Args` / `Result` | Pydantic | `BaseModel` | request + response schemas |
