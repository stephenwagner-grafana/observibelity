#!/usr/bin/env bash
# Confirm we can talk to a Kubernetes cluster with admin rights.
#
# Each kubectl invocation is wrapped in `timeout 10` so a misconfigured
# context can't hang the installer indefinitely. If the cluster isn't
# reachable we offer four ways forward (k3d, Docker Desktop, custom
# kubeconfig, or bail) instead of just dying.
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

# Compare two semver-ish strings. Returns 0 iff $1 >= $2.
version_ge() {
    local have="$1" want="$2"
    [[ -z "$want" ]] && return 0
    [[ -z "$have" ]] && return 1
    local smallest
    smallest="$(printf '%s\n%s\n' "$have" "$want" | sort -V | head -n1)"
    [[ "$smallest" == "$want" ]]
}

# ---------------------------------------------------------------------------
# 1. cluster-info — is there anything at all on the other end of KUBECONFIG?
# ---------------------------------------------------------------------------
attempt_cluster_info() {
    timeout 10 kubectl cluster-info >/dev/null 2>&1
}

step "check-cluster" "kubectl cluster-info"
tries=0
while ! attempt_cluster_info; do
    tries=$((tries + 1))
    warn "kubectl cannot reach a cluster."
    if [[ "${OBSERVIBELITY_AUTO:-}" == "1" ]]; then
        die "No reachable cluster and OBSERVIBELITY_AUTO=1 — aborting."
    fi
    if [[ "$tries" -ge 3 ]]; then
        die "Cluster still unreachable after 3 attempts. Fix your kubeconfig and re-run."
    fi

    choice="$(ask_choice "How would you like to proceed?" \
        "Create a local k3d cluster (recommended for laptops/demos)" \
        "Use Docker Desktop's Kubernetes (enable in Docker Desktop settings)" \
        "Paste a kubeconfig path I already have" \
        "Exit — I'll bring my own cluster")"

    case "$choice" in
        1)
            log "Bootstrapping local k3d cluster…"
            if [[ -x "$REPO_ROOT/tools/bootstrap-cluster.sh" ]]; then
                # exec replaces this process; on return we'll be back at the
                # top of the loop trying cluster-info again. We use a
                # subshell rather than exec so that the parent main.sh keeps
                # its summary loop intact.
                "$REPO_ROOT/tools/bootstrap-cluster.sh" || warn "bootstrap returned non-zero"
            else
                err "tools/bootstrap-cluster.sh not found or not executable."
            fi
            ;;
        2)
            log "Enable Kubernetes in Docker Desktop → Settings → Kubernetes."
            ask "Press Enter once Docker Desktop reports Kubernetes is running" >/dev/null || true
            ;;
        3)
            kc_path="$(ask "Path to your kubeconfig file")"
            if [[ -r "$kc_path" ]]; then
                export KUBECONFIG="$kc_path"
                log "KUBECONFIG=$KUBECONFIG"
            else
                err "Cannot read $kc_path"
            fi
            ;;
        4|*)
            die "User exited; provide a working kubectl context and re-run."
            ;;
    esac
done

CONTEXT="$(timeout 10 kubectl config current-context 2>/dev/null || echo unknown)"
ok "Connected to context: ${CONTEXT}"

# ---------------------------------------------------------------------------
# 2. can-i create namespace — admin sanity check.
# ---------------------------------------------------------------------------
step "check-cluster" "kubectl auth can-i"
admin_answer="$(timeout 10 kubectl auth can-i create namespace --all-namespaces 2>/dev/null || echo no)"
if [[ "$admin_answer" != "yes" ]]; then
    err "Current user cannot create namespaces. ObserVIBElity needs cluster-admin."
    state_set preflight.cluster.can_admin "false"
    state_set preflight.cluster.context "$CONTEXT"
    exit 1
fi
state_set preflight.cluster.can_admin "true"
ok "Admin access confirmed."

# ---------------------------------------------------------------------------
# 3. Default StorageClass — required unless the user overrode storage.className.
# ---------------------------------------------------------------------------
step "check-cluster" "default StorageClass"
sc_json="$(timeout 10 kubectl get storageclass -o json 2>/dev/null || echo '{"items":[]}')"
DEFAULT_SC="$(jq -r '
    [.items[]
     | select(
         (.metadata.annotations["storageclass.kubernetes.io/is-default-class"] // "false") == "true"
         or (.metadata.annotations["storageclass.beta.kubernetes.io/is-default-class"] // "false") == "true"
       )
     | .metadata.name][0] // empty
' <<< "$sc_json")"

storage_override="${OBSERVIBELITY_STORAGE_CLASSNAME:-}"
if [[ -z "$DEFAULT_SC" && -z "$storage_override" ]]; then
    err "No default StorageClass found and storage.className not overridden in .env."
    err "Set storage.className in .env or mark one of your StorageClasses default."
    state_set preflight.cluster.default_sc ""
    state_set preflight.cluster.context "$CONTEXT"
    exit 1
fi
state_set preflight.cluster.default_sc "${DEFAULT_SC:-$storage_override}"
ok "Default StorageClass: ${DEFAULT_SC:-(override=$storage_override)}"

# ---------------------------------------------------------------------------
# 4. Server version — need a recent-ish API.
# ---------------------------------------------------------------------------
step "check-cluster" "server version"
ver_json="$(timeout 10 kubectl version --output=json 2>/dev/null || echo '{}')"
SERVER_VER="$(jq -r '.serverVersion.gitVersion // empty' <<< "$ver_json" | sed 's/^v//')"
if [[ -z "$SERVER_VER" ]]; then
    err "Could not parse server version from kubectl."
    exit 1
fi

MIN_K8S="1.27"
if ! version_ge "$SERVER_VER" "$MIN_K8S"; then
    err "Server Kubernetes version ${SERVER_VER} is older than required ${MIN_K8S}."
    state_set preflight.cluster.server_version "$SERVER_VER"
    state_set preflight.cluster.context "$CONTEXT"
    exit 1
fi
state_set preflight.cluster.server_version "$SERVER_VER"
state_set preflight.cluster.context "$CONTEXT"
ok "Server version: v${SERVER_VER}"

exit 0
