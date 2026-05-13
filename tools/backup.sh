#!/usr/bin/env bash
# backup.sh — Postgres backup wrapper.
# Phase 0: stub. Phase 1+: runs pg_dump via kubectl exec, gzips, writes to local file.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"

NAMESPACE="${NAMESPACE:-observibelity}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT_FILE="$OUTPUT_DIR/observibelity-$TIMESTAMP.sql.gz"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output|-o) OUTPUT_FILE="$2"; shift 2 ;;
    --namespace|-n) NAMESPACE="$2"; shift 2 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--output FILE] [--namespace NS]

Defaults:
  --output     $OUTPUT_FILE
  --namespace  $NAMESPACE
EOF
      exit 0 ;;
    *) die "Unknown flag: $1" ;;
  esac
done

# Check Postgres pod exists
if ! kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=postgres 2>/dev/null | grep -q "Running"; then
  step "backup" "Phase 0 stub"
  log "No running Postgres pod found in namespace '$NAMESPACE'."
  log "Phase 0 has no Postgres deployment. Phase 1 wires this up."
  log "Once Phase 1 deploys Postgres, this script will run:"
  log "  kubectl exec -n $NAMESPACE postgres-0 -- pg_dumpall -U postgres | gzip > $OUTPUT_FILE"
  exit 0
fi

# Phase 1+ path
step "backup" "Backing up Postgres to $OUTPUT_FILE"
mkdir -p "$(dirname "$OUTPUT_FILE")"
kubectl exec -n "$NAMESPACE" postgres-0 -- pg_dumpall -U postgres 2>/dev/null | gzip > "$OUTPUT_FILE"

if [[ -s "$OUTPUT_FILE" ]]; then
  ok "Backup written: $OUTPUT_FILE ($(du -h "$OUTPUT_FILE" | cut -f1))"
else
  rm -f "$OUTPUT_FILE"
  die "Backup produced empty file; check pg_dumpall output above"
fi
