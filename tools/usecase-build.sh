#!/usr/bin/env bash
# usecase-build.sh — thin shell wrapper around the usecase_build Python pkg.
#
# Bootstraps a venv on first run, installs requirements, then exec's the
# Python module. Any args after the script name are forwarded as-is.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

VENV_DIR="$REPO_ROOT/tools/.venv"
REQS_FILE="$REPO_ROOT/tools/requirements.txt"

# Ensure venv + deps.
if [[ ! -d "$VENV_DIR" ]]; then
    step "usecase-build" "Bootstrapping Python venv"
    if ! command -v python3 >/dev/null 2>&1; then
        die "python3 not found in PATH — install Python 3.11+ first"
    fi
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    if [[ -f "$REQS_FILE" ]]; then
        "$VENV_DIR/bin/pip" install -r "$REQS_FILE" -q
    else
        warn "no requirements.txt at $REQS_FILE; installing minimums"
        "$VENV_DIR/bin/pip" install -q "pydantic>=2.9.0" "pyyaml>=6.0" "jinja2>=3.1.0"
    fi
    ok "venv ready at $VENV_DIR"
fi

# cd into tools/ so the Python module finds usecase_build as a sibling.
cd "$REPO_ROOT/tools"
exec "$VENV_DIR/bin/python" -m usecase_build "$@"
