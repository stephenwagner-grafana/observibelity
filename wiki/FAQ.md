# FAQ

## What does ObserVIBElity actually do?

It installs a **real, working AI application** (NeonCart e-commerce + a
support assistant) onto your Kubernetes cluster, wires all of it to your
Grafana Cloud, and gives you a set of demo scenarios that produce realistic
production failures — slow LLM calls, hallucinated tool arguments, runaway
costs, cascading agent retries. You watch them in **your own** Grafana Cloud
stack.

## How is it different from just deploying Grafana?

Grafana doesn't ship AI workloads. ObserVIBElity is the *workload side* — the
agents, the tools, the LLM gateway, the use cases, the traffic engine — all
emitting real OpenTelemetry GenAI signals so your Grafana stack has something
to observe. It's the AI app that you *put under* Grafana to learn AI
observability.

## What does it cost to run?

Roughly **~$0.05 per demo cycle** on Claude Haiku (Anthropic's cheap tier).
Ollama is free at runtime — you pay only your own electricity. Grafana Cloud
free tier covers a single-user demo comfortably.

## Can I run it without a Grafana Cloud account?

Not in Phase 0. The OTel collector ships to Grafana Cloud, and dashboards +
evaluators are auth-bound to a Grafana stack. Phase 2 may add an "in-cluster
LGTM" option (deploy Mimir/Loki/Tempo locally), but it's not on the immediate
roadmap.

## Can I use OpenAI or Gemini instead of Claude?

Phase 1 ships `AnthropicProvider`. Phase 2 adds `OllamaProvider`. OpenAI and
Gemini are **pluggable** via the `Provider` abstraction — drop a new module
under `tools/deploy_doctor/providers/` and register it in `pyproject.toml`.
The contract is small (auth, list-models, complete, embed). A community PR
adding `OpenAIProvider` is welcome.

## Does it actually deploy AI agents that DO things?

Yes. The specialists call tools that hit Postgres and external APIs. They are
**not** canned-response demos. When the chatbot says "I found 3 mice in stock
in your region," a real specialist called a real `search_products` tool that
hit a real `products` table and filtered by a real `inventory` table. The
trace shows the whole call graph.

## Why does this need GitHub access?

The install forks the canonical repo into your GitHub org so **your**
configs, dashboards, values files, evaluator definitions, and skill catalog
stay in **your** source of truth. The fork is the surface you vibe-edit on.
Pass `--no-fork` to `./install.sh` to skip the fork step if you just want to
kick the tires.

## What's a "use case"?

A **demo scenario** that produces a known failure mode. Examples:
- `mice-rca` — bad fraud check + bad fulfillment args = production cascade
- `email-cascade` — runaway agent retries flood the email tool
- `data-theft-tim` — a malicious persona attempts prompt-injection PII exfil

Each use case registers its own dashboard, alerts, evaluators, and traffic
scenario.

## What's a "specialist"?

A **sub-agent pod** focused on one capability. Examples:
`nc-chatbot` (chat entrypoint), `nc-fraud-detector` (risk scoring),
`sb-policy-finder` (KB lookup). Each specialist has a strict tool allowlist;
it can't call tools it isn't supposed to.

## What's a "tool"?

A **shared microservice** that specialists call to do work — search products,
look up an order, place an order, lookup a policy. Each tool has a
Pydantic-validated `Args` and `Result` schema and is OTel auto-instrumented
(SQLAlchemy, HTTP server, HTTP client).

## What's a "persona"?

A **simulated user** with realistic-but-fake characteristics (name, location,
purchase history, preferences). 150 personas drive the continuous-traffic
engine. They're not real people — the data is generator-produced.

## Will this work with my Helm / Argo CD setup?

Yes. The chart is standard Helm 3. Use `helm template` to render and feed the
output to Argo CD if you prefer git-sync deploys. The `install.sh` wrapper is
optional convenience; the chart itself is the contract.

## Is this production-ready?

**No.** It's a demo. Production deployments would harden secrets (External
Secrets Operator), enable mTLS between pods (Linkerd / Istio), set resource
limits on every pod, replicate Postgres, run dashboards through a
review/approval process, etc. The goal is *observability learning*, not
*production traffic*.

## What's "vibe-editing"?

Modifying `.claude/skills/*` or `registry/*.py` files in **your fork** to
customize the demo — add a new use case, register a new evaluator, retarget
the chatbot for a different industry vertical. Claude Code's vibe-editing
tools regenerate the manifests and redeploy via the skill catalog. Phase 2
ships 6 skills (`build-app`, `build-use-case`, `diagnose-deploy`, etc.).

## Where do I file bugs?

[https://github.com/stephenwagner-grafana/observibelity/issues](https://github.com/stephenwagner-grafana/observibelity/issues)

For deploy failures, run `./tools/deploy-doctor.sh --collect-only` and attach
the resulting `observibelity-failure-*.tar.gz` to your issue. That bundle
contains cluster state, pod logs, recent events, the rendered Helm output, and
the wizard state file — enough to diagnose 95% of failures without a back-and-forth.
