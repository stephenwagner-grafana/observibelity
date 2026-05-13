# ObserVIBElity

ObserVIBElity is a click-to-deploy AI observability demo. It packages a small
e-commerce frontend (NeonCart) and a support assistant (Support Bot) on top of
an LLM gateway, Postgres, and an OpenTelemetry collector wired to Grafana
Cloud. The goal is a single-command install that produces a realistic
multi-service AI application with end-to-end telemetry — so you can poke real
traces, real spans, real LLM generations, and real cost data, in your own
Grafana Cloud stack, in minutes.

## Quick start

```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity
./install.sh
```

The installer runs preflight checks, prompts for the credentials listed in the
[Install guide](Install), and then renders the Helm chart against your current
`kubectl` context.

- [Development guide](Development) — the 4-loop iteration design
- [GitOps](Gitops) — optional Argo CD path

## What's deployed

The full component map — pods, PVCs, network flow, telemetry sinks, and ports
— lives on the [Topology](Topology) page. The "why" behind each piece is on
the [Architecture](Architecture) page.

## Where to deploy

ObserVIBElity targets any Kubernetes 1.27+. See [Deployment Scenarios](Deployment-Scenarios)
for per-target recipes covering Docker Desktop, k3d, k3s, EKS, GKE, AKS, and
"anything else with a working `kubectl`".

## Current status

We are in **Phase 0: scaffolding**. The full delivery roadmap, ticked-off items,
and what's coming in Phase 1 + Phase 2 lives on the [Phase Status](Phase-Status)
dashboard.

## Need help?

- [FAQ](FAQ) — common questions about cost, providers, customization, and how
  the pieces fit together.
- [Troubleshooting](Troubleshooting) — installer failures, pod crash loops,
  missing telemetry, and how to capture a support bundle.
- [Issues](https://github.com/stephenwagner-grafana/observibelity/issues) —
  please attach the `observibelity-failure-*.tar.gz` produced by
  `tools/deploy-doctor.sh --collect-only`.

---

*This wiki is auto-synced from `docs/` in the repo on every push to `main`.
Edit the markdown files in `docs/`, not here.*
