---
name: diagnose-deploy
description: Diagnose ObserVIBElity deployment failures. Use when install.sh exits non-zero, when pods are in CrashLoopBackOff or Pending, when the OTel pipeline is silent, or when the user says "the deploy failed" / "observibelity isn't working" / "pods aren't healthy". Reads cluster state, helm status, pod logs, OTel collector logs; cross-references the architecture spec; suggests fixes. NEVER auto-applies destructive operations — always confirms with the user first.
allowed-tools: Read, Bash, Grep, Glob, WebFetch
---

# diagnose-deploy

A runbook for Claude Code to diagnose ObserVIBElity deployment failures.

## When to use this skill

Use when ANY of:
- `./install.sh` exits with code ≥ 3 (deploy or verify failure)
- `./install.sh verify` reports Failed > 0
- One or more pods in the `observibelity` namespace are not `Ready`
- `observibelity-failure-*.tar.gz` exists in the repo root (deploy-doctor has run)
- The OTel pipeline is silent (no traces/metrics/logs reaching Grafana Cloud)
- The user says "the deploy is broken", "pods aren't healthy", "observibelity isn't working", or similar

Do NOT use when:
- The user is asking how to install fresh — that's `./install.sh` (point them at docs/INSTALL.md)
- The cluster itself is down — that's a kubectl/k3d problem, not an observibelity problem

## What to gather first

Always start with the canonical collector — it bundles everything in one shot:

```
./tools/deploy-doctor.sh --collect-only
```

This writes `observibelity-failure-<timestamp>.tar.gz`. Extract it to a temp dir and read each file. The bundle contains:
- `kubectl_events.yaml` — namespace + cluster-wide events, last 200
- `helm_status.txt` — release state + history
- `pods.yaml` — pod state across the namespace
- `pod_logs/*.log` — per-pod tail of failing containers (init + main)
- `nodes.yaml`, `pvc.yaml` — cluster-side state
- `otel_collector.log` — if the OTel collector exists
- `state.json` — `.observibelity-state` with creds redacted
- `values_rendered.yaml` — what `helm template` would produce

If deploy-doctor isn't available (e.g. on a fresh checkout), run these manually:

```
kubectl get events -n observibelity --sort-by=.lastTimestamp
kubectl get pods -n observibelity -o wide
helm status observibelity -n observibelity --show-resources
```

## How to diagnose

Work in this order:

1. **Find the first failure.** Sort events by time; the FIRST `Warning`/`Error` is usually the root cause; later events are downstream effects.
2. **Trace the failing resource back to its config.** Is it an image pull? Check values.yaml's `global.imageRegistry`. Is it a missing Secret? Check the wizard wrote `.env` correctly. Is it a PVC pending? Check `kubectl get sc` for a default StorageClass.
3. **Read the pod's logs, not just describe.** `kubectl logs <pod> --previous` if the pod restarted.
4. **Check the OTel pipeline last, not first.** A silent OTel collector usually means the upstream app pods aren't ready yet — fix the apps first, telemetry follows.

## Reference docs to consult

When you need to know what a component SHOULD look like:

- **[Live planner](https://claude.wombatwags.com/planner/ai-o11y/)** — the canonical ~240 KB spec. Jump to the section matching the failing component:
  - `01 Apps` — NeonCart / Support Bot config
  - `03 LLM gateway` — gateway routing + Sigil event shape
  - `04 Tools` — Tool class + 13 customization knobs
  - `09 Postgres schema` — 28 tables, datasets per app
  - `10 OTel pipeline` — collector pattern
  - `11 Deployment` — install order, storage backend
- **`/workspace/observibelity/docs/TROUBLESHOOTING.md`** — known failure patterns with fixes
- **`/workspace/observibelity/docs/ARCHITECTURE.md`** — what should be running where
- **`/workspace/observibelity/tools/deploy-doctor/`** — the Python collectors, if you need to extend them
- **`/workspace/observibelity/values.yaml`** — current defaults; the user may have overridden via `.env`

## What to output

A structured diagnosis with these sections:

1. **Symptom** — one sentence: what's broken in the user's terms
2. **Root cause** — your best hypothesis + the specific evidence (line of log, event timestamp, etc.)
3. **Fix** — concrete commands the user can run. Mark each as `[safe]` / `[reversible]` / `[destructive]`.
4. **Confidence** — high / medium / low. Be honest. If low, suggest what additional info would raise it.

Example:

> **Symptom:** Postgres pod stuck in Pending for 4 minutes.
>
> **Root cause:** PVC `postgres-data` is Pending because no StorageClass is set as default. Evidence: `kubectl get pvc -n observibelity` shows `Pending`, `kubectl get sc` shows no `(default)` marker.
>
> **Fix:**
> ```
> # [safe] mark an existing SC as default:
> kubectl patch sc local-path -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
>
> # then [reversible] kick the PVC to retry:
> kubectl delete pod -n observibelity -l app.kubernetes.io/name=postgres
> ```
>
> **Confidence:** high. PVC pending + no default SC is a textbook match.

## What NOT to do

- **Never auto-apply destructive operations.** `kubectl delete`, `helm uninstall`, `helm rollback`, `kubectl drain` — always confirm with the user first.
- **Never read or echo the user's API keys.** They're in `.env` (gitignored) and in Kubernetes Secrets. The redacted `state.json` is fine.
- **Never push to a remote git repo or modify .git/.**
- **Never modify `tests/snapshots/default.golden.yaml`** to "make CI pass." If the snapshot differs, that's a meaningful diff worth investigating.
- **Never bypass preflight failures.** A failed credential check means the user's setup is broken; help them fix the credential, don't tell them to skip preflight.

## Iteration loop

After suggesting a fix:
1. Ask the user to run the suggested commands
2. Ask them to re-run `./install.sh verify`
3. If still failing, re-collect with `./tools/deploy-doctor.sh --collect-only` and repeat
4. After 2 unsuccessful iterations, suggest the user file an issue at https://github.com/stephenwagner-grafana/observibelity/issues with the latest tarball attached
