#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"
source "$REPO_ROOT/tools/lib/state.sh"

# verify.sh — ObserVIBElity component health checks
#
# Phase 0: scaffolding only. Most checks emit a "skipped (Phase 1)" marker
# but the CLI shape, summary line, and exit-code contract are locked in
# so Phase 1 can swap real probes in place without callers noticing.

# --- defaults / flags -------------------------------------------------------

NAMESPACE="observibelity"
JSON_OUT=0

usage() {
  log "Usage: verify.sh [-n|--namespace NS] [--json] [-h|--help]"
  log ""
  log "  -n, --namespace NS    override namespace (default: observibelity)"
  log "      --json            emit results as JSON (suppresses pretty print)"
  log "  -h, --help            show this help"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)
      [[ $# -ge 2 ]] || die "flag $1 requires a value"
      NAMESPACE="$2"
      shift 2
      ;;
    --json)
      JSON_OUT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

# --- counters & results -----------------------------------------------------

PASS=0
SKIP=0
FAIL=0

# Parallel arrays of per-component results for the --json path.
declare -a RESULT_NAMES=()
declare -a RESULT_STATUSES=()
declare -a RESULT_MESSAGES=()

# record_result <component> <status: ok|skip|fail> <message>
record_result() {
  RESULT_NAMES+=("$1")
  RESULT_STATUSES+=("$2")
  RESULT_MESSAGES+=("$3")
}

# Wrappers around the lib/logging.sh helpers so we can suppress styled
# output cleanly when --json is in effect.
emit_checking() {
  [[ "$JSON_OUT" -eq 1 ]] && return 0
  log "  ▸ $1     [checking…]"
}

emit_ok() {
  PASS=$((PASS + 1))
  record_result "$1" "ok" "$2"
  [[ "$JSON_OUT" -eq 1 ]] && return 0
  ok "  ▸ $1     ✓ ready${2:+ — $2}"
}

emit_skip() {
  SKIP=$((SKIP + 1))
  record_result "$1" "skip" "$2"
  [[ "$JSON_OUT" -eq 1 ]] && return 0
  warn "  ▸ $1     ! skipped${2:+ ($2)}"
}

emit_fail() {
  FAIL=$((FAIL + 1))
  record_result "$1" "fail" "$2"
  [[ "$JSON_OUT" -eq 1 ]] && return 0
  err "  ▸ $1     ✗ failed${2:+: $2}"
}

# --- component checks -------------------------------------------------------
# Each function: emit_checking → probe → emit_ok / emit_skip / emit_fail.
# Return 0 on pass/skip, 1 on fail, so callers can chain if desired.

verify_namespace() {
  local name="namespace"
  emit_checking "$name"

  if ! command -v kubectl >/dev/null 2>&1; then
    emit_skip "$name" "kubectl not on PATH"
    return 0
  fi

  if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
    emit_ok "$name" "$NAMESPACE exists"
    return 0
  fi

  # Namespace missing — was deploy even run yet?
  if state_has_passed deploy; then
    emit_fail "$name" "$NAMESPACE not found (deploy ran but namespace gone?)"
    return 1
  fi

  emit_skip "$name" "deploy not run"
  return 0
}

# Phase-1-component stubs. All identical shape: emit_checking → emit_skip.
# Kept as separate functions so Phase 1 can fill each one in independently.
_phase1_stub() {
  local name="$1"
  emit_checking "$name"
  emit_skip "$name" "Phase 1 component — not yet implemented"
  return 0
}

verify_postgres()                  { _phase1_stub "postgres"; }
verify_llm_gateway()               { _phase1_stub "llm-gateway"; }
verify_neoncart()                  { _phase1_stub "neoncart"; }
verify_supportbot()                { _phase1_stub "supportbot"; }
verify_otel_collector()            { _phase1_stub "otel-collector"; }
verify_grafana_cloud_connection()  { _phase1_stub "grafana-cloud"; }

# --- main -------------------------------------------------------------------

[[ "$JSON_OUT" -eq 1 ]] || step "verify" "Running health checks…"

verify_namespace                  || true
verify_postgres                   || true
verify_llm_gateway                || true
verify_neoncart                   || true
verify_supportbot                 || true
verify_otel_collector             || true
verify_grafana_cloud_connection   || true

if [[ "$JSON_OUT" -eq 1 ]]; then
  # Hand-rolled JSON — no jq dependency. RESULT_MESSAGES values are
  # generated locally (no untrusted input) so a minimal escape of
  # backslash + double-quote is sufficient.
  printf '{'
  printf '"namespace":"%s",' "$NAMESPACE"
  printf '"summary":{"ready":%d,"skipped":%d,"failed":%d},' "$PASS" "$SKIP" "$FAIL"
  printf '"results":['
  local_n="${#RESULT_NAMES[@]}"
  for ((i = 0; i < local_n; i++)); do
    [[ $i -gt 0 ]] && printf ','
    esc_name="${RESULT_NAMES[$i]//\\/\\\\}"; esc_name="${esc_name//\"/\\\"}"
    esc_stat="${RESULT_STATUSES[$i]//\\/\\\\}"; esc_stat="${esc_stat//\"/\\\"}"
    esc_msg="${RESULT_MESSAGES[$i]//\\/\\\\}";  esc_msg="${esc_msg//\"/\\\"}"
    printf '{"component":"%s","status":"%s","message":"%s"}' \
      "$esc_name" "$esc_stat" "$esc_msg"
  done
  printf ']}\n'
else
  log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  log "Ready: $PASS  ·  Skipped: $SKIP  ·  Failed: $FAIL"
  log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Exit code: min(FAIL, 99). 0 means everything passed or was skipped.
exit_code=$FAIL
[[ $exit_code -gt 99 ]] && exit_code=99
exit "$exit_code"
