#!/usr/bin/env bash
#
# ObserVIBElity — bootstrap a local k3d cluster for the demo.
#
# Creates a single-node k3d cluster named `observibelity-demo` and wires its
# kubeconfig context. Idempotent: if the cluster already exists, prompts to
# delete and recreate (or `--print-env` to just emit the env without touching
# anything).
#
# Usage:
#   ./bootstrap-cluster.sh             # create the cluster
#   ./bootstrap-cluster.sh --print-env # echo `export KUBECONFIG=...` for eval
#   ./bootstrap-cluster.sh --destroy   # delete the cluster + state
#
# Flags honored from environment:
#   OBSERVIBELITY_NO_INSTALL=1   don't try to install k3d (die if missing)
#   OBSERVIBELITY_AUTO=1         non-interactive (recreate-on-exists = yes)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT

LIB_DIR="$REPO_ROOT/tools/lib"
for lib in colors logging state prompt os; do
    f="$LIB_DIR/${lib}.sh"
    if [[ -f "$f" ]]; then
        # shellcheck disable=SC1090
        source "$f"
    fi
done

state_init 2>/dev/null || true

CLUSTER_NAME="observibelity-demo"

MODE="create"
case "${1:-}" in
    --print-env) MODE="print-env" ;;
    --destroy)   MODE="destroy" ;;
    -h|--help)
        cat <<EOF
Bootstrap a local k3d cluster for ObserVIBElity.

Usage:
  ./bootstrap-cluster.sh             create the cluster
  ./bootstrap-cluster.sh --print-env emit \`export KUBECONFIG=...\` for eval
  ./bootstrap-cluster.sh --destroy   delete the cluster + clear state
EOF
        exit 0
        ;;
    "") ;;
    *) err "unknown argument: $1"; exit 64 ;;
esac

# ─── ensure k3d is installed ─────────────────────────────────────────────────

ensure_k3d() {
    if command -v k3d >/dev/null 2>&1; then
        return 0
    fi
    if [[ "${OBSERVIBELITY_NO_INSTALL:-0}" == "1" ]]; then
        die "k3d is not installed and --no-install was set"
    fi
    log "k3d not found — installing"
    if command -v pkg_install >/dev/null 2>&1; then
        pkg_install k3d || die "pkg_install k3d failed"
    else
        die "no pkg_install helper available; install k3d manually"
    fi
    command -v k3d >/dev/null 2>&1 || die "k3d still not on PATH after install"
}

# ─── modes ───────────────────────────────────────────────────────────────────

mode_print_env() {
    ensure_k3d
    # k3d kubeconfig write returns the path to the kubeconfig file.
    local path
    if ! path=$(k3d kubeconfig write "$CLUSTER_NAME" 2>/dev/null); then
        die "cluster ${CLUSTER_NAME} not found — run \`./bootstrap-cluster.sh\` first"
    fi
    echo "export KUBECONFIG=${path}"
}

mode_destroy() {
    if command -v k3d >/dev/null 2>&1; then
        if k3d cluster list 2>/dev/null | grep -q "^${CLUSTER_NAME}\b"; then
            step "bootstrap" "deleting cluster ${CLUSTER_NAME}"
            k3d cluster delete "$CLUSTER_NAME" >/dev/null 2>&1 || die "k3d cluster delete failed"
            ok "cluster ${CLUSTER_NAME} deleted"
        else
            log "no cluster ${CLUSTER_NAME} present — nothing to delete"
        fi
    else
        warn "k3d not installed — skipping cluster delete"
    fi
    state_set preflight.cluster.bootstrapped "false" 2>/dev/null || true
    state_set preflight.cluster.k3d_name "" 2>/dev/null || true
    ok "state cleared"
}

mode_create() {
    ensure_k3d

    if k3d cluster list 2>/dev/null | grep -q "^${CLUSTER_NAME}\b"; then
        log "cluster ${CLUSTER_NAME} already exists"
        if ask_yn "delete and recreate?" Y; then
            k3d cluster delete "$CLUSTER_NAME" >/dev/null 2>&1 || die "k3d cluster delete failed"
            ok "old cluster deleted"
        else
            log "keeping existing cluster"
            kubectl cluster-info >/dev/null 2>&1 || warn "kubectl cluster-info failed against existing cluster"
            state_set preflight.cluster.bootstrapped "true"
            state_set preflight.cluster.k3d_name "$CLUSTER_NAME"
            return 0
        fi
    fi

    step "bootstrap" "creating k3d cluster ${CLUSTER_NAME}"
    k3d cluster create "$CLUSTER_NAME" \
        --servers 1 \
        --agents 0 \
        --port "8080:80@loadbalancer" \
        --port "8443:443@loadbalancer" \
        --wait \
        || die "k3d cluster create failed"
    ok "cluster ${CLUSTER_NAME} created"

    step "bootstrap" "verifying with kubectl cluster-info"
    if ! kubectl cluster-info >/dev/null 2>&1; then
        die "kubectl cluster-info failed against new cluster"
    fi
    ok "kubectl can reach the cluster"

    state_set preflight.cluster.bootstrapped "true"
    state_set preflight.cluster.k3d_name "$CLUSTER_NAME"
    ok "state updated"

    echo
    log "Next: re-run \`./install.sh\` (or just \`./install.sh preflight\` to confirm)."
}

case "$MODE" in
    create)    mode_create ;;
    print-env) mode_print_env ;;
    destroy)   mode_destroy ;;
esac
