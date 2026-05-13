#!/usr/bin/env bash
# evaluators-sync.sh — sync Sigil/AI Observability evaluators to Grafana Cloud.
#
# Reads registry/_generated/evaluators/*.json (produced by the use-case compiler)
# and creates/updates evaluators via the AI Observability plugin REST API.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

MODE="${1:-status}"
EVAL_DIR="${EVAL_DIR:-$REPO_ROOT/registry/_generated/evaluators}"
GRAFANA_URL="${GRAFANA_URL:-https://${GRAFANA_CLOUD_INSTANCE_NAME:-}.grafana.net}"
GRAFANA_TOKEN="${GRAFANA_TOKEN:-${GRAFANA_CLOUD_API_TOKEN:-}}"
PLUGIN_PATH="/api/plugins/grafana-aiobservability-app/resources"

usage() {
  cat <<EOF
Usage: $0 [push|pull|diff|status]
Sync Sigil evaluators from registry/_generated/evaluators/*.json -> Grafana Cloud.

Env: GRAFANA_URL, GRAFANA_TOKEN (or *_CLOUD_* variants)
EOF
}

cmd_push() {
  [[ -d "$EVAL_DIR" ]] || die "No evaluators directory: $EVAL_DIR. Run 'make build-usecases' first."
  [[ -n "$GRAFANA_TOKEN" ]] || die "GRAFANA_TOKEN required"
  step "push" "Pushing evaluators to ${GRAFANA_URL}"
  local n=0 f=0
  for evfile in "$EVAL_DIR"/*.json; do
    [[ -e "$evfile" ]] || continue
    local name
    name=$(jq -r '.name // "unknown"' "$evfile")
    log "  push $name"
    local code
    code=$(curl -sS -o /tmp/sigil-resp.json -w "%{http_code}" \
      -X POST "${GRAFANA_URL}${PLUGIN_PATH}/evaluators" \
      -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
      -H "Content-Type: application/json" \
      --data-binary @"$evfile")
    if [[ "$code" =~ ^2 ]]; then
      ok "    $name"
      n=$((n+1))
    else
      err "    $name failed ($code): $(head -c 200 /tmp/sigil-resp.json)"
      f=$((f+1))
    fi
  done
  log "Summary: $n pushed, $f failed"
  [[ "$f" -eq 0 ]]
}

cmd_pull() {
  step "pull" "Pulling evaluators from $GRAFANA_URL"
  curl -sS -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
    "${GRAFANA_URL}${PLUGIN_PATH}/evaluators" \
    | jq -c '.[]' | while read -r ev; do
      name=$(echo "$ev" | jq -r '.name')
      mkdir -p "$EVAL_DIR"
      echo "$ev" | jq '.' > "$EVAL_DIR/${name}.json"
      log "  pulled $name"
    done
}

cmd_diff() {
  step "diff" "Comparing local vs remote"
  # Simplified: just list which are new/changed/missing
  log "  (full diff implementation deferred — use jq + curl manually for now)"
}

cmd_status() {
  step "status" "Local at $EVAL_DIR"
  local count=0
  for f in "$EVAL_DIR"/*.json; do
    [[ -e "$f" ]] || continue
    name=$(jq -r '.name // "?"' "$f")
    severity=$(jq -r '.severity // "?"' "$f")
    log "  $name (severity: $severity)"
    count=$((count+1))
  done
  log "Total local: $count"
}

case "$MODE" in
  push|pull|diff|status) cmd_$MODE ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 1 ;;
esac
