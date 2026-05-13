# Developing ObserVIBElity

ObserVIBElity is designed for fast iteration. Pick the right loop for what you're changing.

## The 4 iteration loops

### Loop 1 — Chart + install scripts (sub-30s)

When: editing `install.sh`, `tools/*.sh`, `values.yaml`, `templates/*.yaml`, `Chart.yaml`.

```bash
make test     # fast: bats + pytest + helm-unittest + snapshot diff  (~5-10s)
make dev      # helm upgrade --install --atomic  (~20s on warm cluster)
make verify   # check what's running
```

This is where 80% of Phase 0/1 iteration happens. `make dev` is **idempotent** — same command for first install and every redeploy.

### Loop 2 — App code (Phase 1+, 1-3 min via Skaffold)

When: editing `src/<app>/*.py`, specialist code, tool code, llm-gateway code.

```bash
make watch    # Skaffold: rebuilds image on save, redeploys, streams logs
```

Skaffold watches the source, rebuilds the image (BuildKit cached), imports into k3d's built-in registry (no network round-trip), restarts the Deployment, port-forwards `neoncart` to `localhost:8080`. Logs stream live. Traces appear in your Grafana Cloud Tempo within seconds.

Skaffold profile `docker-desktop` activates automatically when your kubectl context is `docker-desktop` (uses `values-docker-desktop.yaml` overlay).

### Loop 3 — Full smoke (3-8 min)

When: testing the full install path end-to-end.

```bash
make smoke   # ephemeral k3d + ./install.sh --auto + verify + teardown
```

Mirrors what GHA runs on PR merge. If `make smoke` passes locally, it will pass in CI.

### Loop 4 — Production-like (15+ min, gated)

When: validating against a real cloud cluster (EKS / GKE / AKS).

Triggered by nightly GHA workflow + manual `workflow_dispatch`. See `.github/workflows/integration.yml`. Costs real $; runs nightly, not per push.

## Setting up your local dev environment

```bash
make dev-cluster        # creates local k3d cluster + registry (idempotent)
cp .env.example .env    # fill in: Anthropic key, Grafana Cloud creds, GitHub PAT
make dev                # first deploy
make verify             # confirm what's running
make dev-diff           # preview what `make dev` WOULD change (helm diff)
make dev-down           # tear down (keeps cluster)
make dev-cluster-down   # delete cluster
```

## Editing the Helm chart

| file | purpose |
|---|---|
| `Chart.yaml` | chart metadata, kubeVersion gate |
| `values.yaml` | schema + defaults |
| `values-docker-desktop.yaml` | Docker Desktop overlay |
| `templates/_helpers.tpl` | reusable Helm helpers (don't break signatures) |
| `templates/*.yaml` | actual resources |
| `templates/tests/test-connection.yaml` | `helm test` pod (curl smoke) |

To test a chart change:

```bash
# 1. Edit
$EDITOR templates/postgres/statefulset.yaml

# 2. Fast tests
make test                # helm-unittest + snapshot diff

# 3. If snapshot diffs: review carefully, then regenerate
make snapshot
git diff tests/snapshots/default.golden.yaml

# 4. Preview what would change in the cluster
make dev-diff

# 5. Apply
make dev

# 6. Verify
make verify
```

The `--atomic` flag on `make dev` means failed deploys auto-rollback. To inspect a half-deployed state for debugging, set `OBSERVIBELITY_NO_ATOMIC=1 make dev`.

## Editing install.sh / tools/

```bash
# 1. Edit
$EDITOR tools/wizard.sh

# 2. Bash tests
make test-bats

# 3. Real run against your local cluster
./install.sh preflight

# 4. Full smoke if you changed anything load-bearing
make smoke
```

## Editing Python (deploy-doctor, future app code)

```bash
# 1. Edit
$EDITOR tools/deploy_doctor/collect.py

# 2. Unit tests
make test-unit

# 3. Real run
./tools/deploy-doctor.sh --collect-only
```

## Debugging deploy failures

1. **Run deploy-doctor.** `./tools/deploy-doctor.sh --collect-only` produces `observibelity-failure-<timestamp>.tar.gz` with kubectl events, helm status, pod logs, OTel collector logs, redacted state file, and rendered values.
2. **Use the Claude Code skill (optional).** If you have Claude Code installed, the `diagnose-deploy` skill at `.claude/skills/diagnose-deploy/SKILL.md` walks you through structured diagnosis.
3. **Check the troubleshooting guide.** `docs/TROUBLESHOOTING.md` covers common failure patterns with fixes.
4. **File an issue.** https://github.com/stephenwagner-grafana/observibelity/issues with the tarball attached.

## Releasing a new version

```bash
# 1. Update CHANGELOG.md under [Unreleased]
$EDITOR CHANGELOG.md

# 2. Bump version atomically across Chart.yaml + pyproject.toml + CHANGELOG.md
./tools/bump-version.sh 0.2.0

# 3. Commit, tag, push
git commit -am "Release v0.2.0"
git tag v0.2.0
git push --tags
# GHA release workflow triggers → builds images → creates GH release with notes
```

## Common pitfalls

- **Editing `_helpers.tpl`:** signatures are referenced by all other templates. Before renaming or changing params, run `grep -r 'include "observibelity.' templates/` to see what depends on it.
- **Forgetting to regenerate snapshot:** helm-test CI will fail with a diff. Run `make snapshot` after reviewing intentional changes.
- **Editing values.yaml without updating tests:** `tests/helm-unittest/*.yaml` exercises specific paths; new fields need test coverage.
- **Stale `.observibelity-state`:** `./install.sh reset` clears it. Useful when you change creds or want a fresh wizard run.
- **Skaffold deploys to your LOCAL cluster.** Don't use it against production. Use `make dev` or Argo CD for real deploys.
- **`--atomic` rolls back on failure.** Sometimes you want to keep a broken state for diagnosis: `OBSERVIBELITY_NO_ATOMIC=1 make dev`.
- **k3d registry isn't internet:** images you build locally with Skaffold go to k3d's registry, not Docker Hub. To deploy elsewhere, `make images` builds + pushes to ghcr.io.

## Tooling required

| tool | minimum version | install |
|---|---|---|
| kubectl | 1.27 | preflight auto-installs |
| helm | 3.13 | preflight auto-installs |
| k3d | 5.6 | preflight auto-installs (only needed for `dev-cluster`) |
| python | 3.11 | system |
| bash | 4 | system |
| jq | any | preflight auto-installs |
| make | any | system (gnumake on macOS via brew) |
| skaffold (optional) | 2.10+ | `brew install skaffold` / equivalent |
| helm-diff (optional) | 3.9+ | `helm plugin install https://github.com/databus23/helm-diff` |
| bats (optional) | 1.10+ | `apt install bats` / `brew install bats-core` |
| direnv (optional) | any | `brew install direnv`; then `cp .envrc.example .envrc && direnv allow` |

## Project structure

```
observibelity/
├── Chart.yaml · values.yaml · values-docker-desktop.yaml
├── install.sh · uninstall.sh · Makefile · skaffold.yaml
├── templates/        Helm templates (_helpers, namespace, tests/test-connection, …)
├── tools/
│   ├── lib/         shared bash libraries
│   ├── preflight/   environment checks
│   ├── deploy_doctor/  Python diagnostics collector
│   ├── wizard.sh · bootstrap-cluster.sh · verify.sh · …
├── tests/
│   ├── bats/        bash tests for install.sh + libs
│   ├── helm-unittest/ chart template tests
│   ├── pytest/      Python unit tests
│   ├── integration/ cross-component tests (gated to PR-merge + nightly)
│   ├── snapshots/   helm template golden snapshots
│   └── e2e/         smoke-k3d.sh
├── docs/            INSTALL · TROUBLESHOOTING · ARCHITECTURE · PROVIDERS · DEVELOPMENT · GITOPS
├── wiki/            GitHub wiki source (auto-synced)
├── .github/         workflows · ISSUE_TEMPLATE · PULL_REQUEST_TEMPLATE · CODEOWNERS · dependabot · SECURITY
├── .claude/skills/  diagnose-deploy
└── CONTRIBUTING.md · CHANGELOG.md · SECURITY.md · LICENSE · README.md
```

## See also

- [docs/INSTALL.md](INSTALL.md) — installation guide
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — what gets deployed
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common failures + fixes
- [docs/GITOPS.md](GITOPS.md) — optional Argo CD path
- [CONTRIBUTING.md](../CONTRIBUTING.md) — how to submit changes
- [Live planner](https://claude.wombatwags.com/planner/ai-o11y/) — canonical design spec
