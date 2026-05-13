# Scaffold consistency report
Generated: 2026-05-13

## Summary
- 0 executables with missing +x bit (5 library files in `tools/lib/` are intentionally mode 644 — they are sourced, never executed; counted as expected)
- 0 broken internal links
- 0 missing Python imports
- 0 missing bash sources
- 0 missing Helm includes
- 0 gitignore patterns missing
- 0 invalid YAML files
- 2 advisory notes (informational, not failures): `_helpers.tpl` references `.Values.serviceAccount.*` which is not present in `values.yaml` but the helper is never invoked. `dependabot.yml` declares a `docker` ecosystem with no Dockerfiles yet (intentional placeholder).

Overall: all hard checks passed.

## Details

### 1. Executable bits

Hard-required executables (all present, all `0755`):

| file | mode |
|---|---|
| `install.sh` | 755 |
| `uninstall.sh` | 755 |
| `tools/backup.sh` | 755 |
| `tools/bootstrap-cluster.sh` | 755 |
| `tools/bump-version.sh` | 755 |
| `tools/deploy-doctor.sh` | 755 |
| `tools/evaluators-sync.sh` | 755 |
| `tools/restore.sh` | 755 |
| `tools/verify.sh` | 755 |
| `tools/wizard.sh` | 755 |
| `tools/preflight/check-binaries.sh` | 755 |
| `tools/preflight/check-cluster.sh` | 755 |
| `tools/preflight/check-credentials.sh` | 755 |
| `tools/preflight/detect-os.sh` | 755 |
| `tools/preflight/install-tool.sh` | 755 |
| `tools/preflight/main.sh` | 755 |
| `tests/e2e/smoke-k3d.sh` | 755 |

Source-only libraries (intentionally non-executable; sourced via `source "$f"`):

| file | mode | note |
|---|---|---|
| `tools/lib/colors.sh` | 644 | source-only |
| `tools/lib/logging.sh` | 644 | source-only |
| `tools/lib/os.sh` | 644 | source-only |
| `tools/lib/prompt.sh` | 644 | source-only |
| `tools/lib/state.sh` | 644 | source-only |

The `tools/lib/*.sh` files start with `# shellcheck shell=bash` rather than a `#!` shebang and are sourced (never executed) by callers — keeping them mode 644 prevents accidental direct invocation. Treat this as a deliberate convention, not a defect.

### 2. Internal markdown links

All internal links resolve. Verified targets:

| source file | link | target | status |
|---|---|---|---|
| `README.md:61` | `docs/DEVELOPMENT.md` | `docs/DEVELOPMENT.md` | OK |
| `README.md:65` | `docs/ARCHITECTURE.md` | `docs/ARCHITECTURE.md` | OK |
| `README.md:70` | `docs/TROUBLESHOOTING.md` | `docs/TROUBLESHOOTING.md` | OK |
| `README.md:82` | `docs/ARCHITECTURE.md` | `docs/ARCHITECTURE.md` | OK |
| `README.md:83` | `docs/TROUBLESHOOTING.md` | `docs/TROUBLESHOOTING.md` | OK |
| `CONTRIBUTING.md:16` | `docs/DEVELOPMENT.md` | `docs/DEVELOPMENT.md` | OK |
| `CONTRIBUTING.md:109` | `SECURITY.md` | `SECURITY.md` | OK |
| `SECURITY.md:43,49` | `docs/GITOPS.md` | `docs/GITOPS.md` | OK |
| `docs/INSTALL.md:71` | `ARCHITECTURE.md` | `docs/ARCHITECTURE.md` | OK |
| `docs/INSTALL.md:72` | `TROUBLESHOOTING.md` | `docs/TROUBLESHOOTING.md` | OK |
| `docs/DEVELOPMENT.md:201` | `INSTALL.md` | `docs/INSTALL.md` | OK |
| `docs/DEVELOPMENT.md:202` | `ARCHITECTURE.md` | `docs/ARCHITECTURE.md` | OK |
| `docs/DEVELOPMENT.md:203` | `TROUBLESHOOTING.md` | `docs/TROUBLESHOOTING.md` | OK |
| `docs/DEVELOPMENT.md:204` | `GITOPS.md` | `docs/GITOPS.md` | OK |
| `docs/DEVELOPMENT.md:205` | `../CONTRIBUTING.md` | `CONTRIBUTING.md` | OK |
| `docs/ARCHITECTURE.md:104` | `PROVIDERS.md` | `docs/PROVIDERS.md` | OK |
| `docs/ARCHITECTURE.md:105` | `INSTALL.md` | `docs/INSTALL.md` | OK |
| `docs/PROVIDERS.md:63` | `ARCHITECTURE.md` | `docs/ARCHITECTURE.md` | OK |

Wiki links (`wiki/_Sidebar.md`, `wiki/Home.md`) use GitHub-Wiki page-name syntax (`[Topology](Topology)`, `[GitOps](Gitops)`, etc.). These resolve only after the wiki-sync workflow promotes `docs/*` and `wiki/*` into the GitHub Wiki — they are valid wiki references, not filesystem paths, so they are out of scope for filesystem link checking.

### 3. Python imports

All imports resolve to existing modules.

| file:line | import | module/file | status |
|---|---|---|---|
| `__init__.py:2` | `from .collect import Collector` | `tools/deploy_doctor/collect.py` | OK |
| `__init__.py:3` | `from .diagnose import Diagnoser` | `tools/deploy_doctor/diagnose.py` | OK |
| `__init__.py:4` | `from .providers.base import Provider, Suggestion` | `tools/deploy_doctor/providers/base.py` | OK |
| `__main__.py:14` | `from .collect import Collector` | `tools/deploy_doctor/collect.py` | OK |
| `__main__.py:15` | `from .diagnose import Diagnoser` | `tools/deploy_doctor/diagnose.py` | OK |
| `__main__.py:16` | `from .providers import make_provider` | `tools/deploy_doctor/providers/__init__.py` | OK |
| `diagnose.py:13` | `from .collect import Collector` | `tools/deploy_doctor/collect.py` | OK |
| `diagnose.py:14` | `from .providers.base import Provider, Suggestion` | `tools/deploy_doctor/providers/base.py` | OK |
| `providers/__init__.py:6` | `from .base import Provider, Suggestion` | `providers/base.py` | OK |
| `providers/__init__.py:12-13` | `from .anthropic import AnthropicProvider` (lazy) | `providers/anthropic.py` | OK |
| `providers/__init__.py:15-16` | `from .ollama import OllamaProvider` (lazy) | `providers/ollama.py` | OK |
| `providers/anthropic.py:13` | `from .base import Provider, Suggestion` | `providers/base.py` | OK |
| `providers/ollama.py:12` | `from .base import Provider, Suggestion` | `providers/base.py` | OK |

Stdlib imports (`os`, `re`, `argparse`, `subprocess`, `tarfile`, `tempfile`, `datetime`, `sys`, `pathlib`, `typing`, `enum`, `dataclasses`, `abc`) and external pkg imports declared in `tools/requirements.txt` / `tools/pyproject.toml` (`anthropic`, `httpx`, `pydantic`, `pyyaml`) are not validated by path.

### 4. Bash sourcing

All `source "..."` paths resolve to existing files.

| file:line | sourced path | resolves to | status |
|---|---|---|---|
| `install.sh:55` | `$LIB_DIR/${lib}.sh` (5 libs) | `tools/lib/{colors,logging,state,prompt,os}.sh` | OK |
| `install.sh:213` | `$VALUES_FILE` | runtime path (default `.env`) | OK (runtime-resolved) |
| `uninstall.sh:30` | same 5 libs | `tools/lib/*.sh` | OK |
| `tools/bootstrap-cluster.sh:29` | same 5 libs | `tools/lib/*.sh` | OK |
| `tools/wizard.sh:30` | same 5 libs | `tools/lib/*.sh` | OK |
| `tools/wizard.sh:44` | `$ENV_FILE` (`.env`) | runtime-resolved | OK |
| `tools/backup.sh:8` | `tools/lib/logging.sh` | `tools/lib/logging.sh` | OK |
| `tools/restore.sh:8,9` | `lib/logging.sh`, `lib/prompt.sh` | `tools/lib/{logging,prompt}.sh` | OK |
| `tools/verify.sh:4,5` | `lib/logging.sh`, `lib/state.sh` | `tools/lib/{logging,state}.sh` | OK |
| `tools/evaluators-sync.sh:4,5` | `lib/logging.sh`, `lib/state.sh` | `tools/lib/{logging,state}.sh` | OK |
| `tools/bump-version.sh:15` | `lib/logging.sh` | `tools/lib/logging.sh` | OK |
| `tools/deploy-doctor.sh:30` | `lib/logging.sh` | `tools/lib/logging.sh` | OK |
| `tools/preflight/{main,detect-os,check-binaries,check-cluster,check-credentials,install-tool}.sh` | `lib/{logging,state,prompt,os}.sh` | `tools/lib/*.sh` | OK |
| `tools/preflight/check-credentials.sh:25` | `$ENV_FILE` | runtime-resolved | OK |
| `tools/lib/{logging,prompt,state,os}.sh` | `$(dirname "${BASH_SOURCE[0]}")/{colors,logging}.sh` | sibling lib | OK |

### 5. Helm template includes

All `{{ include "..." . }}` calls reference defined named templates in `_helpers.tpl`.

| call site | include | defined at | status |
|---|---|---|---|
| `templates/namespace.yaml:7` | `observibelity.labels` | `_helpers.tpl:36` | OK |
| `templates/tests/test-connection.yaml:4` | `observibelity.fullname` | `_helpers.tpl:13` | OK |
| `templates/tests/test-connection.yaml:6` | `observibelity.labels` | `_helpers.tpl:36` | OK |
| `_helpers.tpl:37` (in labels) | `observibelity.chart` | `_helpers.tpl:29` | OK |
| `_helpers.tpl:38` (in labels) | `observibelity.selectorLabels` | `_helpers.tpl:48` | OK |
| `_helpers.tpl:49` (in selectorLabels) | `observibelity.name` | `_helpers.tpl:4` | OK |
| `_helpers.tpl:58` (in serviceAccountName) | `observibelity.fullname` | `_helpers.tpl:13` | OK (but `serviceAccountName` helper is currently unused) |

### 6. .gitignore coverage

All required patterns are ignored. Current `.gitignore` content:

```
node_modules/
.env
.observibelity-state
.observibelity-state.*.bak
tools/bin/
tools/.venv/
*.tar.gz
observibelity-failure-*.tar.gz
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
*.swp
.vscode/
.idea/
/.kubeconfig
```

| pattern required | present? |
|---|---|
| `.observibelity-state` | yes (line 3) |
| `observibelity-failure-*.tar.gz` | yes (line 8; also covered by `*.tar.gz` on line 7) |
| `tools/bin/` | yes (line 5) |
| `tools/.venv/` | yes (line 6) |
| `__pycache__/` | yes (line 9) |
| `*.pyc` | yes (line 10) |
| `.env` | yes (line 2) |

### 7. GitHub Actions workflow YAML

`pyyaml` is not installed in the sandbox; performed best-effort structural sanity (every file has exactly one `name:`, one `on:`, and one `jobs:` top-level key, balanced brackets, well-formed indentation).

| workflow | name | on | jobs | result |
|---|---|---|---|---|
| `bats.yml` | 1 | 1 | 1 | OK |
| `e2e-smoke.yml` | 1 | 1 | 1 | OK |
| `helm-test.yml` | 1 | 1 | 1 | OK |
| `integration.yml` | 1 | 1 | 1 | OK |
| `lint.yml` | 1 | 1 | 1 | OK |
| `pytest.yml` | 1 | 1 | 1 | OK |
| `release.yml` | 1 | 1 | 1 | OK |
| `wiki-sync.yml` | 1 | 1 | 1 | OK |

`.github/dependabot.yml` and `.github/ISSUE_TEMPLATE/{bug,feature,config}.yml` likewise have balanced brackets and braces (0/0 or matching pairs).

### 8. install.sh cross-reference

`install.sh` references these scripts; every one exists:

| install.sh reference | path | exists? |
|---|---|---|
| `tools/preflight/main.sh` | `tools/preflight/main.sh` | yes (mode 755) |
| `tools/wizard.sh` | `tools/wizard.sh` | yes (mode 755) |
| `tools/deploy-doctor.sh` | `tools/deploy-doctor.sh` | yes (mode 755) |
| `tools/deploy-doctor/main.sh` (fallback path) | n/a | not present, but only used as a fallback when `tools/deploy-doctor.sh` is missing — intentional |
| `tools/verify.sh` | `tools/verify.sh` | yes (mode 755) |

### 9. values.yaml top-level keys vs template references

Active templates use these `.Values.*` paths; all resolve to keys present in `values.yaml`:

| reference | template:line | values.yaml location | status |
|---|---|---|---|
| `.Values.global.namespace` | `templates/namespace.yaml:1,5` | `global.namespace` (line 11) | OK |
| `.Values.phase` | `templates/tests/test-connection.yaml:20,21` | `phase` (line 158) | OK |
| `.Values.nameOverride` | `_helpers.tpl:5,17` | absent → falls back to `.Chart.Name` via `default` (intentional) | OK |
| `.Values.fullnameOverride` | `_helpers.tpl:14,15` | absent → `if` guard skips block (intentional) | OK |
| `.Values.serviceAccount.create` | `_helpers.tpl:57` | absent | advisory (see below) |
| `.Values.serviceAccount.name` | `_helpers.tpl:58,60` | absent | advisory (see below) |

**Advisory note:** the `observibelity.serviceAccountName` helper is defined in `_helpers.tpl` but is never called by any active template. It references `.Values.serviceAccount.{create,name}`, neither of which exists in `values.yaml`. This is dead-code at the moment — not a runtime defect, but Phase 1 should either add `serviceAccount:` to `values.yaml` (and use the helper) or drop the helper.

## Verdict

Hard checks: passed. The scaffold is internally consistent — no broken imports, sources, links, includes, or missing executables. Two minor advisory notes (unused service-account helper; placeholder docker dependabot scan) are left for Phase 1 cleanup.
