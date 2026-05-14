#!/usr/bin/env bash
# dashboards-sync.sh — push dashboards/*.json to Grafana Cloud.
# Uses gcx if available; falls back to curl-based REST calls.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

MODE="${1:-push}"
DASHBOARDS_DIR="${DASHBOARDS_DIR:-$REPO_ROOT/dashboards}"
FILTER="${FILTER:-}"

# Env required for API path
GRAFANA_URL="${GRAFANA_URL:-https://${GRAFANA_CLOUD_INSTANCE_NAME:-}.grafana.net}"
GRAFANA_TOKEN="${GRAFANA_TOKEN:-${GRAFANA_CLOUD_API_TOKEN:-}}"

usage() {
  cat <<EOF
Usage: $0 [push|pull|diff|status]
Push dashboards/*.json to Grafana Cloud.

Env:
  GRAFANA_URL          (or set GRAFANA_CLOUD_INSTANCE_NAME)
  GRAFANA_TOKEN        (or GRAFANA_CLOUD_API_TOKEN)
  DASHBOARDS_DIR       default: $DASHBOARDS_DIR
  FILTER               grep regex on filename
EOF
}

push_one() {
  local f="$1"
  local uid title
  uid=$(jq -r '.uid // empty' "$f")
  title=$(jq -r '.title // empty' "$f")
  [[ -n "$uid" ]] || die "  $f: missing .uid"

  log "  push $uid ($title)"
  local payload
  payload=$(jq -n --slurpfile d "$f" '{dashboard: $d[0], overwrite: true, message: "synced via observibelity dashboards-sync.sh", folderUid: "observibelity"}')

  if command -v gcx >/dev/null 2>&1; then
    gcx dashboards push "$f" 2>&1 | sed 's/^/    /'
  else
    # Direct REST
    local code
    code=$(echo "$payload" | curl -sS -o /tmp/gc-resp.json -w "%{http_code}" \
      -X POST "${GRAFANA_URL}/api/dashboards/db" \
      -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
      -H "Content-Type: application/json" \
      --data-binary @-)
    if [[ "$code" =~ ^2 ]]; then
      ok "    $uid -> $(jq -r '.url // empty' /tmp/gc-resp.json)"
    else
      err "    $uid failed ($code): $(cat /tmp/gc-resp.json)"
      return 1
    fi
  fi
}

cmd_push() {
  [[ -n "$GRAFANA_TOKEN" ]] || die "GRAFANA_TOKEN (or GRAFANA_CLOUD_API_TOKEN) required"
  step "push" "Syncing $DASHBOARDS_DIR -> $GRAFANA_URL"
  local count=0 fail=0
  while IFS= read -r f; do
    [[ -n "$FILTER" ]] && ! basename "$f" | grep -qE "$FILTER" && continue
    if push_one "$f"; then count=$((count+1)); else fail=$((fail+1)); fi
  done < <(find "$DASHBOARDS_DIR" -name "*.json" -type f)
  log "Summary: $count pushed, $fail failed"
  [[ "$fail" -eq 0 ]]
}

cmd_pull() {
  [[ -n "$GRAFANA_TOKEN" ]] || die "GRAFANA_TOKEN required"
  step "pull" "Pulling all dashboards from $GRAFANA_URL -> $DASHBOARDS_DIR"
  # List dashboards by tag = "ai-observability"
  local hits
  hits=$(curl -sS -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
    "${GRAFANA_URL}/api/search?tag=ai-observability&type=dash-db")
  echo "$hits" | jq -r '.[] | "\(.uid) \(.title)"' | while read -r uid title; do
    log "  pull $uid ($title)"
    curl -sS -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
      "${GRAFANA_URL}/api/dashboards/uid/${uid}" \
      | jq '.dashboard' > "$DASHBOARDS_DIR/${uid}.json"
  done
  ok "done"
}

cmd_diff() {
  [[ -n "$GRAFANA_TOKEN" ]] || die "GRAFANA_TOKEN required"
  step "diff" "Comparing local $DASHBOARDS_DIR vs remote"
  while IFS= read -r f; do
    local uid
    uid=$(jq -r '.uid' "$f")
    local remote
    remote=$(curl -sS -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
      "${GRAFANA_URL}/api/dashboards/uid/${uid}" 2>/dev/null \
      | jq '.dashboard')
    if [[ -n "$remote" && "$remote" != "null" ]]; then
      if diff -q <(jq -S . "$f") <(echo "$remote" | jq -S .) >/dev/null; then
        ok "  $uid (in sync)"
      else
        warn "  $uid (differs)"
      fi
    else
      err "  $uid (missing remote)"
    fi
  done < <(find "$DASHBOARDS_DIR" -name "*.json")
}

cmd_status() {
  step "status" "Local: $DASHBOARDS_DIR"
  for f in "$DASHBOARDS_DIR"/*.json; do
    [[ -e "$f" ]] || continue
    local uid title
    uid=$(jq -r '.uid // "?"' "$f")
    title=$(jq -r '.title // "?"' "$f")
    log "  $(basename "$f"): uid=$uid title=\"$title\""
  done
}

case "$MODE" in
  push|pull|diff|status) cmd_$MODE ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 1 ;;
esac
