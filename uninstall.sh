#!/usr/bin/env bash
#
# ObserVIBElity — uninstaller.
#
# Reverses what install.sh did. By default it asks before destructive actions
# and preserves the local k3d cluster (if any) so you can re-install quickly.
#
# Usage:
#   ./uninstall.sh [flags]
#
# Flags:
#   --destroy-cluster   Delete the k3d cluster if it was bootstrapped
#   --keep-namespace    Don't delete the `observibelity` namespace
#   --keep-pvc          Don't delete PVCs in the namespace (preserves data)
#   --force             Skip confirmation prompts
#   -h, --help          Print this help and exit

set -euo pipefail

# ─── resolve repo root + source libs ─────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

NAMESPACE="observibelity"
RELEASE="observibelity"
CLUSTER_NAME="observibelity-demo"

# ─── usage ───────────────────────────────────────────────────────────────────

usage() {
    cat <<'EOF'
ObserVIBElity uninstaller — reverses install.sh.

USAGE
  ./uninstall.sh [flags]

FLAGS
  --destroy-cluster   Delete the k3d cluster if it was bootstrapped
  --keep-namespace    Don't delete the `observibelity` namespace
  --keep-pvc          Don't delete PVCs (preserves data)
  --force             Skip confirmation prompts
  -h, --help          Print this help and exit
EOF
}

# ─── arg parsing ─────────────────────────────────────────────────────────────

DESTROY_CLUSTER=0
KEEP_NAMESPACE=0
KEEP_PVC=0
FORCE=0

while (( $# )); do
    case "$1" in
        --destroy-cluster) DESTROY_CLUSTER=1; shift ;;
        --keep-namespace)  KEEP_NAMESPACE=1;  shift ;;
        --keep-pvc)        KEEP_PVC=1;        shift ;;
        --force)           FORCE=1;           shift ;;
        -h|--help)         usage; exit 0 ;;
        *)
            err "unknown argument: $1"
            usage
            exit 64
            ;;
    esac
done

if (( FORCE )); then
    export OBSERVIBELITY_AUTO=1
fi

# ─── confirm ─────────────────────────────────────────────────────────────────

CTX="$(kubectl config current-context 2>/dev/null || echo "<no kubectl context>")"

if (( ! FORCE )); then
    if ! ask_yn "Uninstall observibelity from context ${CTX}?" Y; then
        log "aborted"
        exit 0
    fi
fi

REMOVED=()

# ─── helm release ────────────────────────────────────────────────────────────

if command -v helm >/dev/null 2>&1; then
    if helm status "$RELEASE" -n "$NAMESPACE" >/dev/null 2>&1; then
        step "uninstall" "removing helm release ${RELEASE}"
        if helm uninstall "$RELEASE" -n "$NAMESPACE" --wait >/dev/null 2>&1; then
            ok "helm release removed"
            REMOVED+=("helm release ${RELEASE}")
        else
            warn "helm uninstall failed (continuing)"
        fi
    else
        log "no helm release named ${RELEASE} in ${NAMESPACE} — skipping"
    fi
else
    warn "helm not installed — skipping helm release removal"
fi

# ─── PVCs ────────────────────────────────────────────────────────────────────

if (( ! KEEP_PVC )); then
    if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
        pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null || true)
        if [[ -n "$pvcs" ]]; then
            step "uninstall" "deleting PVCs in ${NAMESPACE}"
            if kubectl delete pvc -n "$NAMESPACE" --all >/dev/null 2>&1; then
                ok "PVCs removed"
                REMOVED+=("PVCs in ${NAMESPACE}")
            else
                warn "PVC deletion failed (continuing)"
            fi
        else
            log "no PVCs to remove in ${NAMESPACE}"
        fi
    fi
else
    log "--keep-pvc: leaving PVCs in place"
fi

# ─── namespace ───────────────────────────────────────────────────────────────

if (( ! KEEP_NAMESPACE )); then
    if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
        step "uninstall" "deleting namespace ${NAMESPACE}"
        if kubectl delete namespace "$NAMESPACE" >/dev/null 2>&1; then
            ok "namespace removed"
            REMOVED+=("namespace ${NAMESPACE}")
        else
            warn "namespace deletion failed (continuing)"
        fi
    else
        log "no namespace ${NAMESPACE} present — skipping"
    fi
else
    log "--keep-namespace: leaving ${NAMESPACE} in place"
fi

# ─── cluster ─────────────────────────────────────────────────────────────────

if (( DESTROY_CLUSTER )); then
    if kubectl config get-contexts 2>/dev/null | grep -q "${CLUSTER_NAME}"; then
        if command -v k3d >/dev/null 2>&1; then
            step "uninstall" "destroying k3d cluster ${CLUSTER_NAME}"
            if k3d cluster delete "${CLUSTER_NAME}" >/dev/null 2>&1; then
                ok "k3d cluster destroyed"
                REMOVED+=("k3d cluster ${CLUSTER_NAME}")
            else
                warn "k3d cluster delete failed (continuing)"
            fi
        else
            warn "k3d not installed but --destroy-cluster requested — skipping"
        fi
    else
        log "no kubectl context for ${CLUSTER_NAME} — skipping cluster destroy"
    fi
fi

# ─── state file ──────────────────────────────────────────────────────────────

STATE_FILE="$REPO_ROOT/.observibelity-state"
if [[ -f "$STATE_FILE" ]]; then
    warn "about to remove ${STATE_FILE}"
    rm -f "$STATE_FILE"
    REMOVED+=("state file .observibelity-state")
    ok "state file removed"
fi

# ─── summary ─────────────────────────────────────────────────────────────────

echo
log "Summary — removed:"
if (( ${#REMOVED[@]} )); then
    for item in "${REMOVED[@]}"; do
        echo "  - $item"
    done
else
    echo "  (nothing — no observibelity resources found)"
fi
echo

ok "Done."
