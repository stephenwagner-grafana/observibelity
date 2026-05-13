#!/usr/bin/env bash
# alerts-sync.sh — push Prometheus alerting rules to Grafana Cloud Mimir.
#
# Reads registry/_generated/alerts/*.yaml (one rule group per use case,
# produced by tools/usecase-build.sh) and POSTs each to Mimir's rule API:
#
#   POST /api/v1/rules/<namespace>/<group>
#
# This is the Grafana Cloud path. For in-cluster Prometheus, set
# .Values.alerts.target=prometheus-operator (or configmap-only) and let
# the Helm chart ship PrometheusRule / ConfigMap objects instead.
#
# CI: this script is invoked by .github/workflows/sync.yml; locally use
#     `make alerts-push` (see Makefile).
#
# Env:
#   GRAFANA_URL                  Full Mimir/alerting base URL (preferred), or
#   GRAFANA_CLOUD_INSTANCE_NAME  short instance slug (we derive URL)
#   GRAFANA_TOKEN                Bearer token (preferred), or
#   GRAFANA_CLOUD_API_TOKEN      legacy var name
#   NAMESPACE                    Mimir namespace for the rule groups
#                                (default: observibelity)
#   ALERTS_DIR                   Override the input directory
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

ALERTS_DIR="${ALERTS_DIR:-$REPO_ROOT/registry/_generated/alerts}"
GRAFANA_URL="${GRAFANA_URL:-https://${GRAFANA_CLOUD_INSTANCE_NAME:-}.grafana.net}"
GRAFANA_TOKEN="${GRAFANA_TOKEN:-${GRAFANA_CLOUD_API_TOKEN:-}}"
NAMESPACE="${NAMESPACE:-observibelity}"

usage() {
    cat <<EOF
Usage: $0 [push|status]
Pushes registry/_generated/alerts/*.yaml to Grafana Cloud Mimir alerting.

Commands:
  push     POST each rule group to the Mimir alerting API
  status   List local alert files (no network)

Endpoint pattern: POST \${GRAFANA_URL}/api/v1/rules/\${NAMESPACE}/<group>
Requires: GRAFANA_TOKEN (or GRAFANA_CLOUD_API_TOKEN).
EOF
}

cmd_push() {
    [[ -n "$GRAFANA_TOKEN" ]] || die "GRAFANA_TOKEN required (or GRAFANA_CLOUD_API_TOKEN)"
    [[ -d "$ALERTS_DIR" ]] || die "alerts dir not found: $ALERTS_DIR — run 'make build-usecases' first"
    step "push" "Pushing alerts → $GRAFANA_URL (namespace: $NAMESPACE)"
    local n=0 f=0 name code
    for af in "$ALERTS_DIR"/*.yaml; do
        [[ -e "$af" ]] || continue
        name=$(basename "$af" .yaml)
        log "  push $name"
        code=$(curl -sS -o /tmp/alert-resp -w "%{http_code}" \
            -X POST "${GRAFANA_URL}/api/v1/rules/${NAMESPACE}/${name}" \
            -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
            -H "Content-Type: application/yaml" \
            --data-binary @"$af") || code="000"
        if [[ "$code" =~ ^2 ]]; then
            ok "    $name"
            n=$((n + 1))
        else
            err "    $name failed ($code) — $(head -c 200 /tmp/alert-resp 2>/dev/null || true)"
            f=$((f + 1))
        fi
    done
    log "Summary: $n pushed, $f failed"
    [[ "$f" -eq 0 ]] || exit 1
}

cmd_status() {
    step "status" "Local at $ALERTS_DIR"
    if [[ ! -d "$ALERTS_DIR" ]]; then
        warn "alerts dir not found — run 'make build-usecases' first"
        return 0
    fi
    local count=0
    for f in "$ALERTS_DIR"/*.yaml; do
        [[ -e "$f" ]] || continue
        echo "  $(basename "$f")"
        count=$((count + 1))
    done
    log "Total: $count alert group(s)"
}

case "${1:-status}" in
    push) cmd_push ;;
    status) cmd_status ;;
    -h | --help) usage; exit 0 ;;
    *) usage; exit 1 ;;
esac
