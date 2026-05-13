#!/usr/bin/env bash
# evaluators-sync.sh — sync Sigil/AI Observability evaluators to Grafana Cloud.
#
# Reads registry/_generated/evaluators/*.json (produced by the use-case compiler)
# and creates/updates evaluators via the AI Observability plugin REST API.
#
# NOTE (Sigil v0.17.0): the grafana-sigil-app plugin does not yet expose
# evaluator CRUD under /resources. Until it does, `push` and `pull` will
# return "404 page not found" and the script reports it cleanly. The
# canonical evaluator specs live at registry/use_cases/*.yaml and must be
# created manually via the Grafana UI (see docs/EVALUATORS.md).

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

MODE="${1:-status}"
EVAL_DIR="${EVAL_DIR:-$REPO_ROOT/registry/_generated/evaluators}"
GRAFANA_URL="${GRAFANA_URL:-https://${GRAFANA_CLOUD_INSTANCE_NAME:-}.grafana.net}"
GRAFANA_TOKEN="${GRAFANA_TOKEN:-${GRAFANA_CLOUD_API_TOKEN:-}}"
PLUGIN_PATH="/api/plugins/grafana-sigil-app/resources"

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
  [[ -n "$GRAFANA_TOKEN" ]] || die "GRAFANA_TOKEN required"
  step "pull" "Pulling evaluators from $GRAFANA_URL"
  local code body
  body=$(mktemp)
  code=$(curl -sS -o "$body" -w "%{http_code}" \
    -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
    "${GRAFANA_URL}${PLUGIN_PATH}/evaluators")
  if [[ ! "$code" =~ ^2 ]]; then
    err "GET /evaluators -> $code: $(head -c 200 "$body")"
    rm -f "$body"
    log "Sigil v0.17.0 does not yet expose evaluator CRUD; see docs/EVALUATORS.md for manual UI flow."
    return 1
  fi
  if ! jq -e 'type == "array"' "$body" >/dev/null 2>&1; then
    err "Response is not an array: $(head -c 200 "$body")"
    rm -f "$body"
    return 1
  fi
  mkdir -p "$EVAL_DIR"
  local n=0
  while read -r ev; do
    local name
    name=$(echo "$ev" | jq -r '.name // empty')
    [[ -n "$name" ]] || { warn "    skipping evaluator with no name"; continue; }
    echo "$ev" | jq '.' > "$EVAL_DIR/${name}.json"
    log "  pulled $name"
    n=$((n+1))
  done < <(jq -c '.[]' "$body")
  rm -f "$body"
  log "Total pulled: $n"
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
