# Installing ObserVIBElity

## Prerequisites
- A Kubernetes cluster (k3s, EKS, GKE, AKS, k3d) >= 1.27, OR Docker Desktop with Kubernetes enabled
- `kubectl` >= 1.27 with admin permissions on the target cluster
- `helm` >= 3.13
- `gh` (GitHub CLI) — optional, only if you let `install.sh` fork the repo for you
- `jq`, `git`, `bash` >= 4, `python3` >= 3.11, `curl`
- Disk: ~2 GiB for images + 1 GiB for Postgres
- Memory: 4 GiB minimum on the cluster

If any of these are missing, `install.sh preflight` will offer to install them locally into `./tools/bin/` (no sudo, no system changes). Pass `--system-install` to use your OS package manager instead.

## Credentials
You'll need three accounts. The wizard will link out to each:
- **Anthropic** — https://console.anthropic.com/settings/keys. ~$5 of credit is enough for the demo.
- **Grafana Cloud** — https://grafana.com/auth/sign-up/create-user (free tier suffices). After signing up: stack -> Connections -> Data sources -> OpenTelemetry -> grab the OTLP endpoint, instance ID, and API token.
- **GitHub** — a personal access token with `repo` scope from https://github.com/settings/tokens/new?scopes=repo. Needed to fork the canonical repo into your org. Pass `--no-fork` to skip.

## Quick start
```
git clone https://github.com/stephenwagner-grafana/observibelity.git
cd observibelity
./install.sh
```

The wizard walks 6 prompts. Total time from clone to working demo: ~10 min on a warm cluster.

## What `install.sh` does
1. **preflight** — detects OS + binaries; offers to install missing ones locally; validates cluster admin + default StorageClass; validates every credential with a live API call.
2. **wizard** — interactive prompts for any missing inputs; writes `.env` (chmod 600); validates again.
3. **deploy** — `helm install observibelity .` (Phase 0: stub; Phase 1 implements).
4. **verify** — health-checks each component; prints summary table.

## Phase 0 status
The current release is **Phase 0: scaffolding only**. `preflight` and `wizard` are fully functional and validate your environment. `deploy` prints "Phase 0 — scaffolding only" and exits. `verify` reports which components exist. This lets you confirm your prereqs + creds before Phase 1 ships the actual demo.

## Subcommands
| command | does |
|---|---|
| `./install.sh preflight` | run preflight checks only |
| `./install.sh wizard` | run the wizard only (gather creds) |
| `./install.sh deploy` | run deploy only (Phase 0: stub) |
| `./install.sh verify` | run health checks |
| `./install.sh doctor` | collect diagnostics into a tarball |
| `./install.sh reset` | clear `.observibelity-state` and start fresh |
| `./install.sh` (no args) | run preflight -> wizard -> deploy -> verify |

## Flags
| flag | does |
|---|---|
| `--auto` | non-interactive; require `.env` populated |
| `--no-install` | don't auto-install missing tools; just print install commands |
| `--no-fork` | skip GitHub fork step |
| `--system-install` | use OS package manager (`brew`/`apt`/`dnf`) for missing tools |
| `--skip <phase>` | skip a phase; repeatable |
| `--reset` | clear `.observibelity-state` and start fresh |
| `--values <file>` | load values overrides (default: `.env`) |
| `-h`, `--help` | print usage |

## State file
`./.observibelity-state` (JSON) tracks which phases passed. Re-running `./install.sh` resumes from where you left off. `--reset` wipes it. Each input is stored as a sha256 hash, not the raw value, so the file is safe to share.

## Exposing apps publicly (NeonCart + Support Bot)

The chart produces a plain `Ingress` per frontend when you set the host. How that hostname resolves to the cluster is your problem to solve — pick one of the patterns below.

### Pattern A — chart-bundled Cloudflare Tunnel (declarative)

Best when you want hostnames + routes versioned in `values.yaml`.

```bash
# one-time, from the machine you'll deploy from
cloudflared tunnel login
cloudflared tunnel create observibelity   # prints a UUID
cloudflared tunnel route dns observibelity neoncart.example.com
cloudflared tunnel route dns observibelity support.example.com

# create the credentials Secret
kubectl create ns observibelity
kubectl -n observibelity create secret generic cloudflared-credentials \
  --from-file=credentials.json=$HOME/.cloudflared/<UUID>.json
```

Then in `values-deploy.yaml`:
```yaml
neoncart:
  ingress: { enabled: true, className: traefik, host: neoncart.example.com }
supportbot:
  ingress: { enabled: true, className: traefik, host: support.example.com }
cloudflareTunnel:
  enabled: true
  tunnelId: "<UUID-from-cloudflared-tunnel-create>"
  ingress:
    - hostname: neoncart.example.com
      service: http://neoncart.observibelity.svc.cluster.local:80
    - hostname: support.example.com
      service: http://supportbot.observibelity.svc.cluster.local:80
```

Re-run `helm upgrade` and the chart's bundled `cloudflared` Deployment picks up the routes. Hostnames + routes round-trip through git — `tools/dashboards-sync.sh push` style consistency.

### Pattern B — existing tunnel managed in the Cloudflare dashboard (token-style)

Best when you already run `cloudflared` outside the chart (e.g. with `--token`) and prefer the Zero Trust UI for route management.

1. Leave `cloudflareTunnel.enabled: false` in values.
2. Set `<app>.ingress.host` for each frontend you want exposed.
3. In **Cloudflare Zero Trust → Networks → Tunnels → [your tunnel] → Public Hostnames**, add:
   - `neoncart.example.com` → `http://neoncart.observibelity.svc.cluster.local:80`
   - `support.example.com` → `http://supportbot.observibelity.svc.cluster.local:80`

Adding the public hostname auto-creates a CNAME on Cloudflare's DNS. Validate with `curl https://neoncart.example.com/`.

### Pattern C — your own ingress controller (no tunnel)

If the cluster has a public LoadBalancer + DNS pointing at it (e.g. EKS + Route53), just set `<app>.ingress.host` and `<app>.ingress.className` and you're done. Cert-manager handles TLS.

### Verifying it works

```bash
curl -sS -o /dev/null -w "neoncart: %{http_code}\n" https://neoncart.example.com/
curl -sS -o /dev/null -w "support:  %{http_code}\n" https://support.example.com/
```

Both should return `200`. If you get `530`/`1033`, the tunnel can't reach the Service — check `kubectl -n observibelity logs deploy/cloudflared` (Pattern A) or your existing cloudflared logs (Pattern B).

## Uninstall
```
./uninstall.sh
./uninstall.sh --destroy-cluster   # also deletes the k3d cluster
```

## Next steps
- Read [docs/ARCHITECTURE.md](ARCHITECTURE.md) to understand the components
- Read [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) if anything fails
- See the [full system planner](https://claude.wombatwags.com/planner/ai-o11y/) for the design rationale
