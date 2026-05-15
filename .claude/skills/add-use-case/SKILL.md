---
name: add-use-case
description: Author a new ObserVIBElity use case via conversation. Use when the user says "add a use case", "new use case", "build a demo scenario", or describes a behavior they want to detect/alert on. Generates the bundled YAML at registry/use_cases/<name>.yaml; runs the compiler; deploys via make dev.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# add-use-case

A skill for authoring new ObserVIBElity use cases through conversation.

## When to trigger

When the user says ANY of:
- "Add a use case"
- "New use case"
- "Build a demo scenario where..."
- "I want to detect/alert on X"
- "Add an evaluator + dashboard for Y"

OR they describe behavior they want to observe (e.g. "I want to catch when employees paste credit cards into Support Bot").

## Skip if

- The user is asking to MODIFY an existing use case — use the edit-use-case workflow instead (or just `$EDITOR registry/use_cases/<name>.yaml`)
- The user is asking about Phase 1 components (apps, specialists, tools) — those are different skills

## What to do

### Step 1: Read context

Always read FIRST:
- `docs/USE-CASES.md` — the authoring guide
- `registry/use_cases/_example.yaml` — the schema reference
- `tools/usecase_build/schema.py` — the Pydantic source of truth
- 1-2 existing use case YAMLs from `registry/use_cases/*.yaml` as examples

### Step 2: Gather requirements via conversation

Don't ask 13 questions in a row. Have a conversation:
1. **What's the use case?** (the user describes the behavior)
2. **Which app?** NeonCart / Support Bot / Both (often inferable from context)
3. **Which archetype fits?** Propose one based on the description and ask the user to confirm. Show the 5 options with one-line descriptions:
   - `trace-and-fix` — One trace surfaces it (rare in practice; mostly mice-RCA)
   - `per-user-pattern` — Sticky offender, leaderboard pattern (Tim/Mara/Jordan/Priya)
   - `leaderboard` — Rate/count ranked across categories (Model Winner, Quality Trend)
   - `single-event-severity` — ANY critical event fires (PII echo, hiring-discrim)
   - `cascade` — Counter > N per session (Email Cascade, Token Spikes)
4. **Centerpiece?** Worth promoting to a featured demo with SLO? Default no.
5. **Severity?** low/medium/high/critical
6. **Persona** (if per-user-pattern or cascade): give it a u-<name>-<role> ID

### Step 3: Generate the YAML

Use `Write` to create `registry/use_cases/<name>.yaml`. Fill in scenario + evaluator + dashboard + alert sections based on the archetype's template. Use kebab-case for name. Set kind, k6_template, panels_from_template, condition all per the archetype's conventions.

For the evaluator `spec` field: write a real Sigil expression based on the user's described behavior. Examples by archetype:
- `trace-and-fix`: `error.span_name = "{{trace_filter}}" AND error.message =~ "{{error_pattern}}"`
- `per-user-pattern`: `count(messages.persona_id = "{{persona}}" AND msg.matches_pattern("{{signature}}")) >= {{n}} IN 15m`
- `single-event-severity`: `severity = critical AND event.name = "{{event_pattern}}"`
- `cascade`: `count_per_session(tool.name = "{{tool}}") > {{threshold}}`

### Step 4: Validate + compile

Run:
```bash
./tools/usecase-build.sh --input registry/use_cases/<name>.yaml --validate-only
```

If it fails, read the error, fix the YAML, retry. Don't ask the user to fix Pydantic errors; iterate yourself until it passes.

Then run the full compile:
```bash
./tools/usecase-build.sh --input registry/use_cases/<name>.yaml
```

### Step 5: Show plan + ask permission to deploy

Print a summary:
```
Use case authored: data-theft-tim
  Archetype: per-user-pattern
  Persona: tim.lewis@acme.com
  Scenarios: 1 (tim_exfil)
  Evaluators: 1 (data-theft-tim.bulk_pii_request)
  Dashboard: ai-obs-data-theft-tim
  Alerts: 1 (data-theft-tim.detection)

Compiled artifacts:
  registry/_generated/evaluators/data-theft-tim.bulk_pii_request.json
  registry/_generated/dashboards/ai-obs-data-theft-tim.json
  registry/_generated/alerts/data-theft-tim.yaml
  registry/_generated/scenarios/data-theft-tim.tim_exfil.js

Deploy to your cluster now? (Y/n)
```

If yes: `make dev` (which redeploys with the new artifacts).

If no: just confirm the YAML was saved.

### Step 6: Verify

After deploy:
- Check pods Ready: `make verify`
- Check evaluator/alert presence in Grafana Cloud (mention how — Sigil UI for evaluator, alerting rules section for alert)
- Tell user how to trigger the demo manually (use the `demo.do` field from the YAML)

## What NOT to do

- Don't write Sigil expressions you're guessing at without context — ask the user to confirm
- Don't deploy without permission (the `make dev` step)
- Don't commit to git automatically — user does that
- Don't modify the schema (`tools/usecase_build/schema.py`) — request changes to the source code instead
- Don't bypass archetype validation (e.g. don't mark centerpiece=true without an SLO)
- Don't reuse a use case name; if user wants to update an existing one, edit the file directly

## Iteration

If the first cut isn't right:
1. Re-read the user's intent (often they had a specific scenario in mind)
2. Edit the YAML, not start over
3. Re-run compile + verify

## See also
- `docs/USE-CASES.md` — full authoring guide
- `tools/usecase-templates/<archetype>/README.md` — archetype-specific parameter docs
- `registry/use_cases/_example.yaml` — annotated example
- Live planner § 06 Use cases — full design context
