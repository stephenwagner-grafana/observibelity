#!/usr/bin/env bash
# ObserVIBElity preflight orchestrator.
#
# Runs each preflight check in order, collects pass/fail results, then prints
# a punch list at the end. Exits 0 iff every check passed.
#
# NOTE: install.sh is responsible for `chmod +x` on these scripts when the
# repo is freshly cloned (Write tool cannot set the executable bit).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"
# shellcheck source=../lib/state.sh
source "$REPO_ROOT/tools/lib/state.sh"
# shellcheck source=../lib/prompt.sh
source "$REPO_ROOT/tools/lib/prompt.sh"
# shellcheck source=../lib/os.sh
source "$REPO_ROOT/tools/lib/os.sh"

PREFLIGHT_DIR="$REPO_ROOT/tools/preflight"

state_init

# Each entry: "<name>|<status>|<detail>" where status is one of pass/fail/warn.
declare -a RESULTS=()

# Run a check script. Captures its exit code; never aborts the orchestrator
# itself even with `set -e` because we explicitly tolerate non-zero returns.
run_check() {
    local name="$1"
    local script="$2"
    shift 2
    step "$name" "running $(basename "$script")"
    local rc=0
    bash "$script" "$@" || rc=$?
    if [[ "$rc" -eq 0 ]]; then
        RESULTS+=("$name|pass|")
        ok "$name passed"
    else
        RESULTS+=("$name|fail|exit=$rc")
        err "$name failed (exit $rc)"
    fi
    return 0
}

run_check "detect-os"        "$PREFLIGHT_DIR/detect-os.sh"
run_check "check-binaries"   "$PREFLIGHT_DIR/check-binaries.sh"
run_check "check-cluster"    "$PREFLIGHT_DIR/check-cluster.sh"
run_check "check-credentials" "$PREFLIGHT_DIR/check-credentials.sh"

# ---------------------------------------------------------------------------
# Build summary from state + results.
# ---------------------------------------------------------------------------
total=${#RESULTS[@]}
passed=0
for r in "${RESULTS[@]}"; do
    status="${r#*|}"; status="${status%%|*}"
    [[ "$status" == "pass" ]] && passed=$((passed + 1))
done

# Pretty values pulled from state where available.
os_val="$(state_get preflight.os 2>/dev/null || echo "unknown")"
distro_val="$(state_get preflight.distro 2>/dev/null || echo "")"
sc_val="$(state_get preflight.cluster.default_sc 2>/dev/null || echo "")"
server_ver="$(state_get preflight.cluster.server_version 2>/dev/null || echo "")"

# Binaries: extract a compact list from the JSON we wrote.
bin_summary="$(state_get preflight.binaries 2>/dev/null \
    | jq -r 'to_entries | map("\(.key) \(.value.version // "?")") | join(", ")' 2>/dev/null \
    || echo "")"

# Credentials: count validated of the ones we know about.
creds_validated=$(state_get preflight.creds 2>/dev/null \
    | jq '[.[] | select(.validated == "true")] | length' 2>/dev/null || echo 0)
creds_total=$(state_get preflight.creds 2>/dev/null \
    | jq 'length' 2>/dev/null || echo 0)

log ""
log "Preflight summary:"

# OS row.
detect_status="$(printf '%s\n' "${RESULTS[@]}" | grep '^detect-os|' | cut -d'|' -f2)"
if [[ "$detect_status" == "pass" ]]; then
    log "  ✓ OS detected: ${os_val} (${distro_val})"
else
    log "  ✗ OS detection failed"
fi

# Binaries row.
bin_status="$(printf '%s\n' "${RESULTS[@]}" | grep '^check-binaries|' | cut -d'|' -f2)"
if [[ "$bin_status" == "pass" ]]; then
    log "  ✓ Binaries: ${bin_summary:-ok}"
else
    log "  ✗ Binaries: missing or stale — see errors above"
fi

# Cluster row.
clu_status="$(printf '%s\n' "${RESULTS[@]}" | grep '^check-cluster|' | cut -d'|' -f2)"
if [[ "$clu_status" == "pass" ]]; then
    log "  ✓ Cluster: ${server_ver:-ok}${sc_val:+, default SC=$sc_val}"
else
    log "  ✗ Cluster: see errors above"
fi

# Credentials row.
cred_status="$(printf '%s\n' "${RESULTS[@]}" | grep '^check-credentials|' | cut -d'|' -f2)"
if [[ "$cred_status" == "pass" ]]; then
    log "  ✓ Credentials: ${creds_validated} of ${creds_total} validated"
else
    log "  ✷ Credentials: ${creds_validated} of ${creds_total} validated"
fi

log ""
log "${passed} of ${total} checks passed."

if [[ "$passed" -eq "$total" ]]; then
    state_mark_passed phase.preflight
    ok "Preflight complete."
    exit 0
else
    err "Fix the above and re-run \`./install.sh preflight\`."
    exit 1
fi
