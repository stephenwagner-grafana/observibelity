#!/usr/bin/env bash
# import-from-demo-pack.sh — read the legacy /workspace/ai-o11y-demo-pack
# Python UseCase classes and emit a bundled YAML per use case under
# registry/use_cases/<name>.yaml.
#
# Idempotent: skips files that already exist (prints a warning). Run with the
# demo-pack path as $1 (defaults to /workspace/ai-o11y-demo-pack).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

DEMO_PACK="${1:-/workspace/ai-o11y-demo-pack}"

[[ -d "$DEMO_PACK" ]] || die "Demo pack not found at $DEMO_PACK"
[[ -d "$DEMO_PACK/registry/use_cases" ]] || die "Demo pack missing registry/use_cases at $DEMO_PACK"

step "Importing use cases" "from $DEMO_PACK"

if [[ ! -d "$REPO_ROOT/tools/.venv" ]]; then
    log "Bootstrapping tools/.venv (one-time)"
    python3 -m venv "$REPO_ROOT/tools/.venv"
    "$REPO_ROOT/tools/.venv/bin/pip" install --upgrade pip -q
    "$REPO_ROOT/tools/.venv/bin/pip" install -r "$REPO_ROOT/tools/requirements.txt" -q
fi

cd "$REPO_ROOT/tools"
exec ./.venv/bin/python -m usecase_build.importer "$DEMO_PACK"
