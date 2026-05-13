# Contributing to ObserVIBElity

Thanks for considering a contribution. This guide covers everything you need to submit a PR.

## Getting started

```bash
git clone https://github.com/<your-fork>/observibelity.git
cd observibelity
make dev-cluster        # creates local k3d
cp .env.example .env    # fill in creds
make dev
make verify
```

Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the 4-loop iteration design.

## Before you code

- **Open an issue first** for non-trivial changes — keeps everyone aligned and avoids wasted effort
- **Check the planner** at https://claude.wombatwags.com/planner/ai-o11y/ for context on architectural decisions
- **Check `.github/PROJECTS.md`** for in-flight work and recommended Project board structure

## Code style

| language | tool | config |
|---|---|---|
| Bash | shellcheck | `.shellcheckrc` (severity: warning) |
| Python | ruff + ruff-format | `tools/pyproject.toml` |
| YAML | yamllint | `.yamllint` |
| Helm | helm lint | strict mode |
| Markdown | none (just be consistent) | n/a |

Run pre-commit hooks locally:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Testing

Before pushing, run:

```bash
make test    # fast: ~10s, runs in CI on every PR
make smoke   # full: ~5min, runs in CI on PR merge
```

PRs that don't pass `make test` will be auto-rejected by CI.

For Phase 1+ changes that touch app code, also run:

```bash
make watch   # Skaffold in another terminal while you test interactively
```

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add OllamaProvider with model rotation
fix: preflight crash when /etc/os-release missing
docs: add EKS deployment scenario to wiki
chore: bump python from 3.11 to 3.12 in pytest matrix
refactor: extract redaction helper from collect.py
test: add helm rollback integration test
```

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `style`.

## Pull request workflow

1. **Branch from `main`:** `git checkout -b feat/something-meaningful`
2. **Make focused commits:** one logical change per PR
3. **Update CHANGELOG.md:** add a line under `## [Unreleased]` for user-facing changes
4. **Update docs:** if behavior changed, update `docs/*.md` (wiki auto-syncs from there)
5. **Pass tests:** `make test` locally, then push and let CI confirm
6. **Open PR using the template:** describe what + why + how + testing
7. **Reference the issue:** `Closes #N` in the description

## What goes where

| change | file(s) |
|---|---|
| New install flag | `install.sh` + `tests/bats/install.bats` + `docs/INSTALL.md` + `CHANGELOG.md` |
| New chart value | `values.yaml` + `tests/helm-unittest/values_test.yaml` + `tests/snapshots/default.golden.yaml` (regen via `make snapshot`) + `CHANGELOG.md` |
| New Provider | `tools/deploy_doctor/providers/<name>.py` + `tools/pyproject.toml` (entry point) + `tests/pytest/test_providers.py` + `docs/PROVIDERS.md` + `CHANGELOG.md` |
| New troubleshooting entry | `docs/TROUBLESHOOTING.md` only |
| Architecture change | `docs/ARCHITECTURE.md` + `wiki/Topology.md` + planner update |

## Issue templates

Use the templates at `.github/ISSUE_TEMPLATE/`:

- **Bug report:** include `observibelity-failure-*.tar.gz` from `./tools/deploy-doctor.sh --collect-only`
- **Feature request:** describe the problem first, then the proposed solution

## Code of Conduct

This project follows the [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be excellent to each other.

## Questions

- **Discussions:** https://github.com/stephenwagner-grafana/observibelity/discussions
- **Bugs:** https://github.com/stephenwagner-grafana/observibelity/issues
- **Security:** see [SECURITY.md](SECURITY.md)
