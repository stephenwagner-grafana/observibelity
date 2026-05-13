#!/usr/bin/env bash
# deploy-doctor.sh — diagnostic collector + LLM-driven diagnoser wrapper.
#
# Phase 0: ships a tarball of cluster diagnostics the user attaches to a
# GitHub issue. Phase 1: wires the same Provider abstraction the llm-gateway
# will use and asks Claude/Ollama to diagnose.
#
# Naming: this wrapper is `deploy-doctor.sh` (hyphen). The Python package it
# launches is `deploy_doctor` (underscore). Both refer to the same thing.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve REPO_ROOT (the directory containing Chart.yaml).
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
export REPO_ROOT

# ---------------------------------------------------------------------------
# Source shared logging helpers if present (best-effort; this script must
# stand alone if logging.sh is missing, since deploy-doctor is the recovery
# tool people reach for when the install is half-broken).
#
# The shared lib exposes: log / ok / warn / err / die / step. We provide
# minimal stderr-only fallbacks with matching names.
# ---------------------------------------------------------------------------
if [[ -f "$REPO_ROOT/tools/lib/logging.sh" ]]; then
    # shellcheck source=/dev/null
    source "$REPO_ROOT/tools/lib/logging.sh"
else
    log()  { printf '[OBS] %s\n' "$*" >&2; }
    ok()   { printf '[OBS] OK: %s\n' "$*" >&2; }
    warn() { printf '[OBS] WARN: %s\n' "$*" >&2; }
    err()  { printf '[OBS] ERROR: %s\n' "$*" >&2; }
    die()  { err "$*"; exit 1; }
fi

# ---------------------------------------------------------------------------
# Venv bootstrap. We keep a marker file `.installed-YYYYMMDD` so we can detect
# when requirements.txt has changed and trigger a re-install.
# ---------------------------------------------------------------------------
VENV_DIR="$REPO_ROOT/tools/.venv"
REQ_FILE="$REPO_ROOT/tools/requirements.txt"

needs_install() {
    [[ ! -d "$VENV_DIR" ]] && return 0
    [[ ! -x "$VENV_DIR/bin/python" ]] && return 0

    # If any marker exists and is newer than requirements.txt, we're fresh.
    local newest_marker
    newest_marker="$(ls -t "$VENV_DIR"/.installed-* 2>/dev/null | head -n1 || true)"
    if [[ -z "$newest_marker" ]]; then
        return 0
    fi
    if [[ "$REQ_FILE" -nt "$newest_marker" ]]; then
        return 0
    fi
    return 1
}

if needs_install; then
    if [[ ! -d "$VENV_DIR" ]]; then
        log "Creating venv at $VENV_DIR"
        python3 -m venv "$VENV_DIR"
    else
        log "requirements.txt changed; re-installing into $VENV_DIR"
    fi
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet -r "$REQ_FILE"
    # Drop the old marker(s) so only the newest stamp survives.
    rm -f "$VENV_DIR"/.installed-* 2>/dev/null || true
    touch "$VENV_DIR/.installed-$(date +%Y%m%d)"
fi

# ---------------------------------------------------------------------------
# Activate venv (PATH-style; we don't need full `source activate` semantics).
# ---------------------------------------------------------------------------
export PATH="$VENV_DIR/bin:$PATH"

# ---------------------------------------------------------------------------
# Default args: if the caller passed nothing, behave as a collector and write
# a tarball next to the repo root with a timestamped name.
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
    DEFAULT_OUTPUT="$REPO_ROOT/observibelity-failure-$(date +%Y%m%d-%H%M%S).tar.gz"
    set -- --collect-only --output "$DEFAULT_OUTPUT"
fi

# ---------------------------------------------------------------------------
# Hand off to the Python package. We cd into tools/ so the package import
# resolves cleanly regardless of where the caller invoked us from.
# ---------------------------------------------------------------------------
cd "$REPO_ROOT/tools"
exec python -m deploy_doctor "$@"
