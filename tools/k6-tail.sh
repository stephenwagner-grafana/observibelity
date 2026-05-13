#!/usr/bin/env bash
# k6-tail.sh — tail k6 traffic engine logs.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

NAMESPACE="${NAMESPACE:-observibelity}"

step "k6" "Tailing k6 traffic engine in $NAMESPACE"
kubectl logs -n "$NAMESPACE" \
  -l app.kubernetes.io/component=traffic \
  -f --tail=100
