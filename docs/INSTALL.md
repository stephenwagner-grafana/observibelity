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

## Uninstall
```
./uninstall.sh
./uninstall.sh --destroy-cluster   # also deletes the k3d cluster
```

## Next steps
- Read [docs/ARCHITECTURE.md](ARCHITECTURE.md) to understand the components
- Read [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) if anything fails
- See the [full system planner](https://claude.wombatwags.com/planner/ai-o11y/) for the design rationale
