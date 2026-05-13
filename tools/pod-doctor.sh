#!/usr/bin/env bash
# pod-doctor.sh — quick health snapshot of observibelity pods.
# For each failing pod: print last 20 log lines + last 5 events.
set -uo pipefail
NAMESPACE="${NAMESPACE:-observibelity}"

echo "▸ Pod status:"
kubectl get pods -n "$NAMESPACE" -o wide
echo ""

echo "▸ Pods not Ready:"
kubectl get pods -n "$NAMESPACE" -o json \
  | jq -r '.items[] | select(.status.containerStatuses == null or (.status.containerStatuses[] | .ready == false)) | .metadata.name' \
  | while read -r pod; do
      echo ""
      echo "━━━ $pod ━━━"
      kubectl describe pod -n "$NAMESPACE" "$pod" 2>&1 \
        | grep -A4 "State:\|Last State:\|Reason:" \
        | head -20
      echo "-- last 20 lines --"
      kubectl logs -n "$NAMESPACE" "$pod" --tail=20 --all-containers 2>&1 \
        | head -25 \
        || echo "(logs unavailable)"
    done

echo ""
echo "▸ Recent events:"
kubectl get events -n "$NAMESPACE" --sort-by=.lastTimestamp 2>&1 \
  | grep -iE "warn|fail|err" \
  | tail -10
