# Provider plugins

## Why a Provider abstraction
ObserVIBElity routes every LLM call through a centralized `llm-gateway` pod. Specialists never see the provider directly — they emit `gen_ai.*` OTel attributes and hand off to the gateway, which selects a Provider and a model. This means:
- **Multi-vendor without code changes** — swap Claude for Gemini per-deploy via `values.yaml`
- **Cost control in one place** — caching, rate limiting, fallback live in the gateway
- **Lockstep model rotation** — all Ollama-bound specialists rotate models in 5-min windows (locked decision)
- **Deploy-doctor uses the same providers** — eat your own dogfood

## The Provider base class
```python
# tools/deploy-doctor/providers/base.py
class Provider(ABC):
    def __init__(self, config: dict | None = None): ...

    @abstractmethod
    def diagnose(self, context: dict, system_prompt: str) -> list[Suggestion]:
        ...
```

The same shape will be used by the eventual llm-gateway (with `complete(prompt, tools)` instead of `diagnose`).

## Built-in providers (Phase 0/1)
| name | module | model default | notes |
|---|---|---|---|
| `anthropic` | `deploy_doctor.providers.anthropic` | `claude-haiku-4-5-20251001` | requires `ANTHROPIC_API_KEY` |
| `ollama` | `deploy_doctor.providers.ollama` | `llama3.1:8b` | requires `OLLAMA_BASE_URL`; off by default |

In Phase 0 both providers raise `NotImplementedError` on `diagnose()` — only the signatures are locked in. Phase 1 wires the actual calls.

## Adding a new provider
1. Create `tools/deploy-doctor/providers/<name>.py` with a `<Name>Provider(Provider)` class
2. Register the entry point in `tools/pyproject.toml`:
   ```toml
   [project.entry-points."observibelity.providers"]
   <name> = "deploy_doctor.providers.<name>:<Name>Provider"
   ```
3. The `make_provider("<name>")` factory in `providers/__init__.py` picks it up live
4. Add to `values.yaml` under `llmGateway.providers.<name>:` for the gateway

## Cost considerations
- **Claude (Haiku)**: ~$0.25/M input, ~$1.25/M output tokens. Demo workload: ~$0.05 per `./install.sh deploy -> verify` cycle.
- **Claude (Sonnet)**: ~$3/M input, ~$15/M output. Use for higher-quality demos; ~$0.30 per cycle.
- **Ollama**: free at runtime; requires a host with sufficient VRAM. Default lockstep rotation uses 2 loaded models, 5-min cycle.
- deploy-doctor defaults to Haiku for cheap diagnostics.

## Canonical label policy

**TL;DR:** Sigil owns Anthropic/OpenAI/Google pricing — the gateway never overrides it. Our local `pricing.json` table still fuels custom dashboards for Ollama and any non-Sigil-licensed model, but for Anthropic, the AI Observability plugin's Cost panel reads numbers computed inside Sigil itself.

### Why
The user directive (2026-05-13) was *"Sigil owns prod license and makes sure configs follow default labels so every dashboard panel shows and is correlated."* That maps to four concrete rules:

1. **Sigil is the source of truth for licensed-provider cost.** When a generation event hits Sigil from a provider Sigil tracks (`anthropic`, `openai`, `google`, `gemini`, `cohere`, `bedrock`), we omit `gen_ai.usage.cost.*` from the event so Sigil computes it. For everything else (Ollama, custom models) we still emit our GPU-amortized estimate so the plugin's Cost panel isn't empty.
2. **Stick to OTel GenAI semantic conventions.** Every generation event carries the canonical attrs the plugin's default panels expect — `gen_ai.system`, `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.request.max_tokens`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cached_input_tokens`, `gen_ai.response.finish_reasons`.
3. **Conversation grouping uses `session.id` + `gen_ai.conversation.id`.** Both are derived from `persona_id + UTC hour` so multi-turn chats from the same loadgen persona group into one conversation. Phase 3 will thread a real `X-Session-Id` header browser-side.
4. **User attribution uses `user.id` + `enduser.id`.** Mirrored from `ai_o11y.persona_id`. The `ai_o11y.*` attrs stay for the existing 12 custom dashboards; the canonical equivalents land alongside.

### Service identity (resource attrs)
Every FastAPI service in the stack (`llm-gateway`, `neoncart`, `supportbot`, specialists, tools) declares the same resource shape on its OTel TracerProvider + MeterProvider:

```
service.name=<component>
service.namespace=observibelity
service.instance.id=<pod hostname>
deployment.environment=<demo|production|staging|dev>   # from global.deploymentEnvironment
telemetry.sdk.name=opentelemetry
```

`global.deploymentEnvironment` (defaults to `demo`) is a chart value plumbed through `OTEL_RESOURCE_ATTRIBUTES` and a `DEPLOYMENT_ENVIRONMENT` env var. Set it to `production` in `values-deploy.yaml` for prod stacks so the AI Observability plugin's environment filter can carve them apart.

### Trace correlation
The Sigil event emitter (`src/llm-gateway/app/sigil.py`) pulls `trace_id` + `span_id` from the active OTel span when the caller doesn't pass them explicitly — so every event sent to Sigil ingest can be drilled-down into the matching Tempo trace and the matching Loki log line filtered by `{namespace="observibelity"} | trace_id="<id>"`.

### The cost-strip predicate
```python
_SIGIL_LICENSED_PROVIDERS = frozenset({
    "anthropic", "openai", "google", "gemini", "cohere", "bedrock",
})

def _should_emit_cost(provider: str | None) -> bool:
    """True iff WE compute cost; False iff Sigil owns it for this provider."""
    return (provider or "").strip().lower() not in _SIGIL_LICENSED_PROVIDERS
```

When adding a new provider whose pricing Sigil tracks, add it to that set in `sigil.py` *and* drop the row from `pricing.py` to avoid stale local estimates leaking into anything that calls `compute_cost`.

## Provider selection at runtime
```yaml
# values.yaml
llmGateway:
  providers:
    anthropic:
      enabled: true
      model: claude-haiku-4-5-20251001
    ollama:
      enabled: false
      baseUrl: http://192.168.1.50:11434
      models: [llama3.1:8b, qwen2.5:7b]   # for lockstep rotation
```

## See also
- [Live planner § 03 LLM gateway](https://claude.wombatwags.com/planner/ai-o11y/#llm-gateway) for the gateway design
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) for where Providers fit in the system
