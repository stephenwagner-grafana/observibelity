#!/usr/bin/env bash
# restore.sh — Postgres restore wrapper.
# Phase 0: stub. Phase 1+: gunzip + pipe to psql via kubectl exec.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"
source "$REPO_ROOT/tools/lib/prompt.sh"

NAMESPACE="${NAMESPACE:-observibelity}"
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force|-f) FORCE=1; shift ;;
    --namespace|-n) NAMESPACE="$2"; shift 2 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--force] [--namespace NS] <backup-file.sql.gz>

Restores a Postgres backup into the running cluster.
EOF
      exit 0 ;;
    -*) die "Unknown flag: $1" ;;
    *) BACKUP_FILE="$1"; shift ;;
  esac
done

[[ -n "${BACKUP_FILE:-}" ]] || die "Usage: $0 <backup-file.sql.gz>"
[[ -f "$BACKUP_FILE" ]] || die "Backup file not found: $BACKUP_FILE"

if ! kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=postgres 2>/dev/null | grep -q "Running"; then
  step "restore" "Phase 0 stub"
  log "No running Postgres pod found in namespace '$NAMESPACE'."
  log "Phase 0 has no Postgres deployment. Phase 1 wires this up."
  log "Once Phase 1 deploys Postgres, this script will run:"
  log "  gunzip -c $BACKUP_FILE | kubectl exec -i -n $NAMESPACE postgres-0 -- psql -U postgres"
  exit 0
fi

# Phase 1+ path
if [[ "$FORCE" -ne 1 ]]; then
  warn "This will OVERWRITE the running database in namespace '$NAMESPACE'."
  ask_yn "Continue?" N || die "Aborted."
fi

step "restore" "Restoring $BACKUP_FILE -> Postgres in $NAMESPACE"
gunzip -c "$BACKUP_FILE" | kubectl exec -i -n "$NAMESPACE" postgres-0 -- psql -U postgres

ok "Restore complete."
