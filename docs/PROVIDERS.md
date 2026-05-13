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
