# Authoring use cases

ObserVIBElity uses a **registry-driven** model for use cases: one YAML per use case under `registry/use_cases/` describes scenarios, evaluators, dashboard, alerts, and SLO together. A compiler reads each YAML and emits all derived artifacts.

This page covers how to author a new use case.

## Authoring surfaces (pick one)

| Surface | Best for | Effort |
|---|---|---|
| **Copy + edit YAML** | "I want one like email_cascade but with $X different" | seconds |
| **`tools/new-usecase.sh`** | Guided interactive wizard with archetype picker | ~1 min |
| **`.claude/skills/add-use-case`** | Conversational — describe in English, Claude generates YAML | ~2 min |
| **Web wizard** at `wizard/usecase.html` | Customer-facing demo authoring | ~3 min |

All four produce the same YAML format. The compiler is shared.

## The bundled YAML

Each use case lives at `registry/use_cases/<name>.yaml`. See `_example.yaml` for an annotated template. The schema is at `tools/usecase_build/schema.py` (Pydantic 2).

Top-level fields:
- `name` (kebab-case, required)
- `title` (human-readable, required)
- `app` (`neoncart` | `supportbot` | `both`, required)
- `phase` (0 | 1 | 2, required)
- `centerpiece` (bool, default false)
- `archetype` (one of 5; see below)
- `description` (paragraph)
- `scenarios` (list — k6 traffic)
- `evaluators` (list — Sigil specs)
- `dashboard` (single dashboard config)
- `alerts` (list — Prometheus rules)
- `slo` (optional; required if `centerpiece=true`)
- `demo` (do/signal/sell — used in the planner's tables and DEMO_RUNBOOK)

## The 5 archetypes

| Archetype | When to use | Examples |
|---|---|---|
| `trace-and-fix` | One trace ID, one error span, one fix | mice-rca |
| `per-user-pattern` | Sticky offender persona; leaderboard | Tim exfil, Mara cowork-term, Jordan disclosure, Priya cost |
| `leaderboard` | Rate/count ranked across categories | Model Winner, Quality Trend, Brand Voice, Hallucination |
| `single-event-severity` | ANY critical event fires alert | PII echo, hiring-discrim, prompt-injection |
| `cascade` | Counter > N per session/minute | Email Cascade, Token Spikes, Tool Runaway |

Each archetype has a template pack at `tools/usecase-templates/<archetype>/` with: `k6_template.js`, `dashboard_panels.json`, `alert_template.yaml`, `evaluator_template.yaml`, `README.md`.

See each archetype's README for parameter details.

## The compile flow

```bash
# Validate one file
./tools/usecase-build.sh --input registry/use_cases/data-theft-tim.yaml --validate-only

# Compile one file (writes derived artifacts to registry/_generated/)
./tools/usecase-build.sh --input registry/use_cases/data-theft-tim.yaml

# Compile all
./tools/usecase-build.sh

# Filter
./tools/usecase-build.sh --filter "data-theft.*"
```

Derived artifacts land in `registry/_generated/`:
- `evaluators/<usecase>.<eval>.json` — Sigil evaluator spec
- `dashboards/<uid>.json` — Grafana dashboard JSON (gcx-deployable)
- `alerts/<usecase>.yaml` — Prometheus alerting rule group
- `scenarios/<usecase>.<scenario>.{js,cm.yaml}` — k6 script + ConfigMap
- `slos/<usecase>.yaml` — OpenSLO definition

Then `make dev` deploys everything (the chart references `registry/_generated/` paths).

## Validation rules

The compiler enforces:
- `name` is kebab-case, alphanumeric + hyphens/underscores
- `phase` is 0 / 1 / 2
- `centerpiece=true` requires `slo` block, ≥1 evaluator, and a dashboard
- `single-event-severity` archetype requires at least one `critical` evaluator
- `leaderboard` archetype requires a dashboard
- `per-user-pattern` archetype requires at least one scenario with `persona` or `persona_filter`
- `cascade` archetype expects ≥2 scenarios (multi-stage)
- All referenced archetypes exist as template directories
- Evaluator `kind` is one of: `rule`, `rubric`, `regex`, `llm-judge`
- Evaluator + scenario + alert names are unique within a use case
- Each alert's `condition` is a non-empty string (real PromQL validation requires a running Prometheus)
- Not all alerts may be `severity: low` (almost certainly a mistake for a demo signal)

## Migrating from the old `ai-o11y-demo-pack`

If you're moving use cases over from `/workspace/ai-o11y-demo-pack/registry/use_cases/*.py`:

```bash
./tools/import-from-demo-pack.sh
# or, with a non-default demo-pack path:
./tools/import-from-demo-pack.sh /path/to/ai-o11y-demo-pack
```

This reads the existing Python class definitions via AST (never executes them), infers the archetype from the demo-pack's `Archetype.*` enum, and writes a bundled YAML to `registry/use_cases/<name>.yaml`. **You'll need to manually review and complete the YAML** — the importer can't infer Sigil expressions or alert thresholds, so it leaves `TODO` markers.

The importer drops use cases removed per the planner: `coworker-termination-intent`, `llm-judge-supervisor`, `least_efficient_user`, `offline-evals-regression`.

Mapping from the demo-pack's broader archetype set to the 5 ObserVIBElity archetypes:

| Demo-pack `Archetype.*` | ObserVIBElity archetype |
|---|---|
| `DETERMINISTIC_RCA` | `trace-and-fix` |
| `PER_USER_PATTERN` | `per-user-pattern` |
| `LEADERBOARD` | `leaderboard` |
| `SINGLE_EVENT_SEVERITY` | `single-event-severity` |
| `PER_SESSION_SEVERITY` | `cascade` |
| `GLOBAL_RATE` | `leaderboard` (rate ranked by category) |
| `REGRESSION_CURVE` | `leaderboard` (rate trend over time) |
| `PER_POLICY_RATE` | `leaderboard` (rate ranked by policy) |

If neither field is set the importer falls back to heuristic keyword detection, then defaults to `leaderboard`.

## Editing an existing use case

Just edit the YAML and re-run the compiler:
```bash
$EDITOR registry/use_cases/<name>.yaml
make build-usecases
make dev
```

The compiler is idempotent. Deleting the YAML file (and running compile) removes the derived artifacts.

## Testing

Two make targets gate use-case quality:

```bash
make test-usecases   # validate every YAML against the schema; no compile
make build-usecases  # validate + compile every YAML
```

`make test` runs the full pytest suite, which includes `tests/pytest/test_usecase_build.py`:

- `TestSchema` — kebab-case name validator, phase range, archetype enum
- `TestCompiler` — centerpiece-requires-SLO, archetype validation rules
- `TestArchetypeTemplates` — every archetype has the 5 required template files
- `TestImporter` — demo-pack AST extraction, archetype mapping, kebab helper, YAML round-trips through the schema

## Adding a new archetype

If the 5 archetypes don't fit your demo:
1. Create `tools/usecase-templates/<your-archetype>/` with the 5 required files
2. Add the archetype name to `tools/usecase_build/schema.py`'s `Archetype` enum
3. Add any archetype-specific validation rules to `compiler.py`'s `validate` method
4. Add a row to the table in this doc
5. Open a PR

## See also
- `registry/use_cases/_example.yaml` — annotated reference
- `tools/usecase_build/schema.py` — source of truth for the schema
- `tools/usecase_build/compiler.py` — cross-cut validations + emitter dispatcher
- `tools/usecase-templates/<archetype>/README.md` — per-archetype docs
- [Live planner § 06 Use cases](https://claude.wombatwags.com/planner/ai-o11y/#use-cases)
- [Live planner § 05 Evaluators](https://claude.wombatwags.com/planner/ai-o11y/#evaluators)
