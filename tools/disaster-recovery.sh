#!/usr/bin/env bash
# disaster-recovery.sh — Tear down a stuck ObserVIBElity deploy.
#
# If a release gets wedged (CrashLoopBackOff cascade, helm stuck, bad PVCs)
# this nukes the Helm release, namespace, and shows you what PVs survived.
# Requires typing the literal word "destroy" to confirm.
#
# After this, re-run `make deploy-k3s-local` to rebuild from scratch.
#
# Usage:
#   ./tools/disaster-recovery.sh
#   NAMESPACE=obs-test ./tools/disaster-recovery.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"
NAMESPACE="${NAMESPACE:-observibelity}"

step "disaster" "Tearing down observibelity (release + ns + PVCs)"
read -p "  Confirm by typing 'destroy': " confirm
[[ "$confirm" == "destroy" ]] || die "Aborted"

/tmp/bin/helm uninstall observibelity -n "$NAMESPACE" --wait || true
kubectl delete namespace "$NAMESPACE" --ignore-not-found --wait
ok "Namespace + release deleted"

log "Persistent volumes:"
kubectl get pv 2>/dev/null | grep -iE "observibelity|postgres-data" || echo "  none"
log "To also remove PVs: kubectl delete pv <name>"
ok "Disaster recovery complete; re-run make deploy-k3s-local to rebuild"
