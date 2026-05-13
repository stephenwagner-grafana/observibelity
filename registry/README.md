# registry/ — declarative source of truth

Registry YAML files describe every component the chart should deploy. The Helm chart's templates loop over these to render Deployments, Services, etc.

## Files

```
registry/
├── apps.yaml          NeonCart + Support Bot (Phase 2)
├── specialists.yaml   all specialists with tool allowlists
├── tools.yaml         all tools with knobs (side_effect, timeout, etc.)
├── use_cases.yaml     10 use cases with evaluators + scenarios
├── evaluators.yaml    26 Sigil evaluators (3 baseline + 23 per-UC)
├── scenarios.yaml     k6 traffic scenarios
├── personas.yaml      persona archetypes (count + offender patterns)
├── slos.yaml          6 SLOs with error budgets
└── alerts.yaml        ~14 alert rules
```

## Conventions

- Every entry has a `name` (kebab-case for use cases, snake_case for tools, slug for everything else)
- Every entry has a `phase` field: 0 (scaffold only) / 1 (mice-rca) / 2 (full)
- The chart's `templates/_components.tpl` loops over these and renders objects only for phase ≤ `.Values.phase`

## Phase 0 status

All files exist as empty stubs (or with the seed entries needed for scaffolding tests). Phase 1 populates the entries for mice-rca; Phase 2 fills in the rest.

## Editing

Use the `.claude/skills/build-use-case` skill (Phase 2) or hand-edit. Validation runs in CI (`tests/registry/validate.py`).

## See also
- [Live planner § 06 Use cases](https://claude.wombatwags.com/planner/ai-o11y/#use-cases)
- [Live planner § OOP hierarchy](https://claude.wombatwags.com/planner/ai-o11y/#oop)
