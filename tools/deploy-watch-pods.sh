#!/usr/bin/env bash
# deploy-watch-pods.sh — Live pod state-change tracer.
#
# Polls `kubectl get pods` every 3s and prints a timestamped line every
# time a pod's state or restart-count changes. Less noisy than
# `kubectl get pods -w` because it suppresses unchanged rows.
#
# Run this alongside `make deploy-k3s-local` to see what's happening
# at every step of the rollout.
#
# Usage:
#   ./tools/deploy-watch-pods.sh                       # default ns
#   NAMESPACE=obs-test ./tools/deploy-watch-pods.sh
set -uo pipefail
NAMESPACE="${NAMESPACE:-observibelity}"

declare -A PREV_STATE
echo "▸ Watching pods in $NAMESPACE (Ctrl-C to stop)"
while true; do
  while IFS= read -r line; do
    name=$(echo "$line" | awk '{print $1}')
    state=$(echo "$line" | awk '{print $3}')
    restarts=$(echo "$line" | awk '{print $4}')
    sig="${state}/${restarts}"
    if [[ "${PREV_STATE[$name]:-}" != "$sig" ]]; then
      echo "[$(date +%H:%M:%S)] $name: ${PREV_STATE[$name]:-NEW} -> $sig"
      PREV_STATE[$name]="$sig"
    fi
  done < <(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null)
  sleep 3
done
