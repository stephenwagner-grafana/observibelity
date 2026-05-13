# llm-gateway — centralized LLM routing

Single FastAPI service that all specialists call. Provides:
- Provider selection (Anthropic / Ollama / future Gemini, OpenAI)
- Model rotation (lockstep 5-min for Ollama-bound specialists)
- Cost tracking (emits `gen_ai.usage.cost.*` metrics)
- Sigil generation events (one per call)
- Tool-use loop (specialists send tool defs, gateway parses tool calls)
- Caching (cache hit/miss tracked as `gen_ai.usage.cached_input_tokens`)

## Phase 1 contract

`POST /v1/complete`
```json
{
  "specialist": "nc-chatbot",
  "messages": [{"role": "user", "content": "..."}],
  "tools": [...],
  "model_override": null,
  "ai_o11y": {
    "usecase": "mice-rca",
    "persona_id": "p-0042",
    "traffic_origin": "interactive"
  }
}
```

Returns the model's response + tool calls + cost.

## Provider plugins

Loaded via Python entry points in `pyproject.toml`:
```toml
[project.entry-points."observibelity.providers"]
anthropic = "llm_gateway.providers.anthropic:AnthropicProvider"
ollama = "llm_gateway.providers.ollama:OllamaProvider"
```

The same `Provider` base class is used by deploy-doctor (eat your own dogfood). See [tools/deploy_doctor/providers/base.py](../../tools/deploy_doctor/providers/base.py).

## OTel attributes (canonical)

Every call emits a span with:
- `gen_ai.system` (anthropic / ollama)
- `gen_ai.request.model`, `gen_ai.response.model`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.usage.cost.input_usd`, `.output_usd`, `.total_usd`
- `gen_ai.response.finish_reasons`

Plus custom:
- `ai_o11y.usecase`, `ai_o11y.persona_id`, `ai_o11y.specialist`
- `traffic_origin` (continuous | interactive)

## See also
- [docs/PROVIDERS.md](../../docs/PROVIDERS.md)
- [Live planner § 03 LLM gateway](https://claude.wombatwags.com/planner/ai-o11y/#llm-gateway)
