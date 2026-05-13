#!/usr/bin/env bash
# Thin wrapper around os.sh's pkg_install with confirmation, progress logging,
# and post-install verification.
#
# Usage: ./install-tool.sh <toolname>
#
# Exit codes:
#   0 — install succeeded and the tool runs
#   1 — install failed, user declined, or post-install verify failed
#   2 — usage error
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"
# shellcheck source=../lib/state.sh
source "$REPO_ROOT/tools/lib/state.sh"
# shellcheck source=../lib/prompt.sh
source "$REPO_ROOT/tools/lib/prompt.sh"
# shellcheck source=../lib/os.sh
source "$REPO_ROOT/tools/lib/os.sh"

if [[ "$#" -ne 1 ]]; then
    err "Usage: $0 <toolname>"
    exit 2
fi

TOOL="$1"

# Per-tool fallback URLs surfaced when install fails — gives the user
# something actionable instead of just an error.
fallback_url() {
    case "$1" in
        kubectl) echo "https://kubernetes.io/docs/tasks/tools/" ;;
        helm)    echo "https://helm.sh/docs/intro/install/" ;;
        k3d)     echo "https://k3d.io/#installation" ;;
        gh)      echo "https://cli.github.com/manual/installation" ;;
        jq)      echo "https://jqlang.github.io/jq/download/" ;;
        git)     echo "https://git-scm.com/downloads" ;;
        python3) echo "https://www.python.org/downloads/" ;;
        curl)    echo "https://curl.se/download.html" ;;
        bash)    echo "https://www.gnu.org/software/bash/" ;;
        *)       echo "https://duckduckgo.com/?q=install+$1" ;;
    esac
}

step "install-tool" "preparing to install $TOOL"

if command -v "$TOOL" >/dev/null 2>&1; then
    ok "$TOOL already installed at $(command -v "$TOOL")"
    exit 0
fi

if [[ "${OBSERVIBELITY_AUTO:-}" != "1" ]]; then
    if ! ask_yn "Install $TOOL into ${REPO_ROOT}/tools/bin/ now?" Y; then
        warn "User declined install of $TOOL."
        exit 1
    fi
fi

log "Installing $TOOL …"
if ! pkg_install "$TOOL"; then
    err "pkg_install failed for $TOOL."
    err "Manual install instructions: $(fallback_url "$TOOL")"
    exit 1
fi

# Post-install verification. `pkg_install` should have put it on PATH (either
# via tools/bin/ or a system package manager). If not, complain loudly.
if ! command -v "$TOOL" >/dev/null 2>&1; then
    err "$TOOL was reported as installed but is not on PATH."
    err "Manual install instructions: $(fallback_url "$TOOL")"
    exit 1
fi

log "Verifying $TOOL …"
if ! "$TOOL" version >/dev/null 2>&1 \
        && ! "$TOOL" --version >/dev/null 2>&1; then
    err "$TOOL is on PATH but failed to report its version."
    err "Manual install instructions: $(fallback_url "$TOOL")"
    exit 1
fi

ok "$TOOL installed and verified ($(command -v "$TOOL"))."
exit 0
