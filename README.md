# ObserVIBElity

## Overview

ObserVIBElity is a click-to-deploy AI observability demo. It packages a small
e-commerce frontend (NeonCart) and a support assistant (Support Bot) on top of
an LLM gateway, Postgres, and an OpenTelemetry collector wired to Grafana
Cloud. The goal is a single-command install that produces a realistic
multi-service AI application with end-to-end telemetry.

## Prerequisites

- A Kubernetes cluster running version 1.27 or newer, or Docker Desktop with
  Kubernetes enabled
- `kubectl` and `helm` available on your PATH
- An Anthropic API key
- A Grafana Cloud account (the free tier is sufficient) with an OTLP endpoint,
  instance ID, and API token
- A GitHub personal access token with `read:packages` scope, used to pull
  images from `ghcr.io/stephenwagner-grafana`

## Quick start

**Or use the web wizard** to generate your `.env` without typing in a terminal: <https://stephenwagner-grafana.github.io/observibelity/wizard/>

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity
./install.sh
```

The installer runs preflight checks, prompts for the credentials listed above,
and then renders the Helm chart against your current `kubectl` context.

## Authoring use cases

ObserVIBElity has a registry-driven, archetype-based use-case system. The 23 planned use cases reduce to 5 archetypes; new ones are one YAML edit.

```bash
make new-usecase              # interactive wizard
# or
./tools/new-usecase.sh <name>
# or open https://stephenwagner-grafana.github.io/observibelity/wizard/usecase.html

# After authoring:
make build-usecases           # compile YAML → derived artifacts
make dev                       # deploy
```

See [docs/USE-CASES.md](docs/USE-CASES.md) for the authoring guide.

If you have Claude Code installed, just say *"add a use case where..."* — the `.claude/skills/add-use-case` skill walks the rest.

## What's deployed

Phase 0: scaffolding only — preflight + wizard + stubs. Helm chart, values
files, and namespace template exist, but no application workloads are
templated yet.

Phase 1 fills in NeonCart and the mice-rca use case (Postgres, llm-gateway,
NeonCart deployment, OTel collector, baseline Grafana Cloud dashboards).

Phase 2 adds Support Bot, k6-driven scenario traffic, and the remaining use
cases.

## Developing

Four iteration loops, one make target each. `make help` lists them all.

```bash
make dev-cluster        # bring up a local k3d cluster (idempotent)
cp .env.example .env    # fill in: Anthropic key, Grafana Cloud creds, GitHub PAT
make dev                # helm upgrade --install --atomic (deploy or redeploy)
make verify             # health-check every component
make test               # fast: bats + pytest + helm-unittest (~10s)
make smoke              # full: ephemeral k3d + install + verify + teardown (~5min)
make watch              # Phase 1+: Skaffold rebuilds images on save
make doctor             # collect diagnostics tarball on a failed deploy
make snapshot           # regenerate the helm template golden snapshot
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full 4-loop guide.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the component diagram,
data flow, and telemetry pipeline.

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for installer failures,
pod crash loops, missing telemetry, and how to capture a support bundle.

## Status

Phase 0 in progress.

## Where to find more

- **[Wiki](https://github.com/stephenwagner-grafana/observibelity/wiki)** — deployment scenarios, topology, FAQ, phase status. Auto-synced from `docs/` on every push to `main`.
- **[Project board](https://github.com/stephenwagner-grafana/observibelity/projects)** — Phase 1/2 backlog, in-flight work, completed milestones.
- **[Issues](https://github.com/stephenwagner-grafana/observibelity/issues)** — bug reports + feature requests. Attach `observibelity-failure-*.tar.gz` from `tools/deploy-doctor.sh --collect-only` for deploy failures.
- **[Architecture](docs/ARCHITECTURE.md)** — what gets deployed and why.
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** — common failure modes + fixes.
- **[Live planner](https://claude.wombatwags.com/planner/ai-o11y/)** — the full ~240 KB design spec (canonical reference).
