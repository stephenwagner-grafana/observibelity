#!/usr/bin/env bash
# Detect the host OS and record it in preflight state.
#
# Detection itself is sourced from tools/lib/os.sh which exports OS_FAMILY,
# OS_ARCH and OS_DISTRO. On any sane Unix this should never fail; we exit 0
# unconditionally so the orchestrator can keep collecting results.
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

state_init

step "detect-os" "inspecting host"
detect_os

# detect_os exports OS_FAMILY/OS_ARCH/OS_DISTRO. Defensive defaults so a
# missing var doesn't tank state with "set -u".
OS_FAMILY="${OS_FAMILY:-unknown}"
OS_ARCH="${OS_ARCH:-unknown}"
OS_DISTRO="${OS_DISTRO:-unknown}"

log "OS_FAMILY=${OS_FAMILY}"
log "OS_ARCH=${OS_ARCH}"
log "OS_DISTRO=${OS_DISTRO}"

state_set preflight.os    "${OS_FAMILY}-${OS_ARCH}"
state_set preflight.distro "${OS_DISTRO}"

ok "Detected ${OS_FAMILY}-${OS_ARCH} (${OS_DISTRO})"
exit 0
