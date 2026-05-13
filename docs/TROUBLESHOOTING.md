# Troubleshooting

## Preflight failures

### "kubectl: command not found"
`preflight` will offer to install kubectl for you. If you declined or passed `--no-install`:
- macOS: `brew install kubectl`
- Ubuntu/Debian: `sudo apt install -y kubectl`
- Fedora/RHEL: `sudo dnf install -y kubectl`
- Or download manually from https://kubernetes.io/docs/tasks/tools/install-kubectl/

### "no default StorageClass"
The cluster has no StorageClass marked `is-default-class`. Fix one of:
- Pass `--set storage.className=<your-sc>` via `--values` or edit `.env`
- Annotate an existing SC: `kubectl patch sc <name> -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'`
- On k3d/Docker Desktop: this should be set automatically. Verify with `kubectl get sc`.

### "Anthropic key rejected (401)"
Check at https://console.anthropic.com/settings/keys:
- Key is active (not revoked)
- Account has billing enabled and balance > $0
- Re-run `./install.sh wizard` to paste a fresh key

### "Grafana Cloud OTLP returned 401"
- Verify the **instance ID** is the numeric stack ID (e.g. `1234567`), not the stack URL
- Verify the **API token** is a Cloud Access Policy token with `metrics:write logs:write traces:write` scopes
- Check the endpoint matches your region: `otlp-gateway-prod-<region>-0.grafana.net/otlp`

### "GitHub fork failed"
- Run `gh auth status` — token must have `repo` scope
- If the token lacks scope, regenerate at https://github.com/settings/tokens/new?scopes=repo
- Skip the fork with `./install.sh --no-fork` if you'd rather fork manually

### "k3d cluster fails to start"
- Port conflict on 8080/8443: check `lsof -iTCP:8080 -sTCP:LISTEN`
- Insufficient Docker memory: increase Docker Desktop's RAM allocation to >= 4 GiB
- Manually clean: `k3d cluster delete observibelity-demo`

## Deploy failures (Phase 1+)

### Pods stuck in `Pending`
`kubectl describe pod -n observibelity <pod>`; look for `PVC pending` (storage issue) or `0/N nodes available` (scheduling).

### `CrashLoopBackOff`
- `kubectl logs -n observibelity <pod> --previous`
- `kubectl describe pod -n observibelity <pod>` for restart count + last termination reason
- Common: missing env var, malformed config, image pull failure

### OTLP pipeline silent (no metrics in Grafana Cloud)
- Check OTel collector logs: `kubectl logs -n observibelity -l app.kubernetes.io/name=otel-collector`
- Verify endpoint reachable: `kubectl exec -n observibelity <pod> -- curl -v <otlp-endpoint>`
- Check token in the collector's Secret: `kubectl get secret -n observibelity otel-creds -o yaml`

## Running deploy-doctor
On any non-preflight failure, `install.sh` auto-runs `tools/deploy-doctor.sh --collect-only`, which writes `observibelity-failure-<timestamp>.tar.gz` to the repo root. The tarball contains:
- kubectl events (namespace + cluster-wide)
- helm status + history
- pod state + logs (failing pods only, last 200 lines per container)
- node state
- PVC state
- OTel collector logs (if present)
- redacted state file and rendered values

Attach this tarball when filing an issue at https://github.com/stephenwagner-grafana/observibelity/issues.

In Phase 1, deploy-doctor will additionally call the Claude API (or Ollama, depending on your provider) to suggest fixes. For Phase 0 it's collection-only.

## Phase 0 known issues
- `deploy` is a stub. This is intentional. Phase 1 fills it in.
- `tools/evaluators-sync.sh` prints "Phase 2 stub" — gcx doesn't support evaluators yet.
- `verify.sh` shows most components as "skipped (Phase 1)".
