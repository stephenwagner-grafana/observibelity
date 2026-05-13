#!/usr/bin/env bash
#
# ObserVIBElity — main installer entry point.
#
# Click-to-deploy AI observability demo. Ties together the phases:
#   preflight → wizard → deploy → verify  (with doctor + reset on demand)
#
# This is Phase 0 scaffolding: `deploy` is a stub that real Phase 1 work will
# replace. `verify` checks what scaffolding currently exists.
#
# Usage:
#   ./install.sh                       # full flow
#   ./install.sh <subcommand> [flags]
#
# Subcommands:
#   preflight    Run preflight checks only
#   wizard       Run interactive (or auto) wizard to populate .env
#   deploy       Deploy the demo via helm upgrade --install
#   verify       Verify the deployed/scaffolded state
#   doctor       Run deploy-doctor (diagnostics, collect logs)
#   reset        Reset persisted state (start over)
#
# Flags:
#   --auto              Non-interactive; sets OBSERVIBELITY_AUTO=1
#   --no-install        Don't auto-install missing tools
#   --no-fork           Skip GitHub fork in wizard
#   --no-atomic         Disable helm --atomic on deploy (failed deploys won't auto-rollback)
#   --system-install    Use OS package manager for missing tools
#   --skip <phase>      Skip a phase (repeatable)
#   --reset             Clear persisted state before running
#   --values <file>     Source environment file (default: .env at repo root)
#   -h | --help         Print this help and exit
#
# Exit codes:
#   0   success
#   1   preflight failed
#   2   wizard cancelled or invalid input
#   3   deploy failed
#   4   verify failed
#   5   deploy-doctor recommended (auto-collected; attach tarball to a GH issue)
#   64  invalid usage

set -euo pipefail

# ─── resolve repo root + source libs ─────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT

LIB_DIR="$REPO_ROOT/tools/lib"
for lib in colors logging state prompt os; do
    f="$LIB_DIR/${lib}.sh"
    if [[ -f "$f" ]]; then
        # shellcheck disable=SC1090
        source "$f"
    fi
done

# state_init is idempotent and safe to call multiple times.
state_init 2>/dev/null || true

# ─── usage ───────────────────────────────────────────────────────────────────

usage() {
    cat <<'EOF'
ObserVIBElity — click-to-deploy AI observability demo.

USAGE
  ./install.sh [flags]                    # full flow: preflight → wizard → deploy → verify
  ./install.sh <subcommand> [flags]

SUBCOMMANDS
  preflight    Run preflight checks only
  wizard       Run interactive (or auto) wizard to populate .env
  deploy       Deploy the demo via helm upgrade --install
  verify       Verify the deployed/scaffolded state
  doctor       Run deploy-doctor (diagnostics, collect logs)
  reset        Reset persisted state (start over)

FLAGS
  --auto              Non-interactive; sets OBSERVIBELITY_AUTO=1
  --no-install        Don't auto-install missing tools
  --no-fork           Skip GitHub fork in wizard
  --no-atomic         Disable helm --atomic on deploy (no auto-rollback on failure)
  --system-install    Use OS package manager for missing tools
  --skip <phase>      Skip a phase (repeatable)
  --reset             Clear persisted state before running
  --values <file>     Source environment file (default: .env at repo root)
  -h, --help          Print this help and exit

EXIT CODES
  0   success
  1   preflight failed
  2   wizard cancelled or invalid input
  3   deploy failed
  4   verify failed
  5   deploy-doctor recommended (tarball collected; attach to a GitHub issue)
  64  invalid usage
EOF
}

# ─── arg parsing ─────────────────────────────────────────────────────────────

SUBCOMMAND=""
SKIPS=()
VALUES_FILE=""
DO_RESET=0

while (( $# )); do
    case "$1" in
        -h|--help)
            usage; exit 0 ;;
        --auto)
            export OBSERVIBELITY_AUTO=1
            shift ;;
        --no-install)
            export OBSERVIBELITY_NO_INSTALL=1
            shift ;;
        --no-fork)
            export OBSERVIBELITY_NO_FORK=1
            shift ;;
        --no-atomic)
            export OBSERVIBELITY_NO_ATOMIC=1
            shift ;;
        --system-install)
            export OBSERVIBELITY_SYSTEM_INSTALL=1
            shift ;;
        --skip)
            [[ $# -ge 2 ]] || { err "--skip requires a phase name"; usage; exit 64; }
            SKIPS+=("$2")
            shift 2 ;;
        --skip=*)
            SKIPS+=("${1#--skip=}")
            shift ;;
        --reset)
            DO_RESET=1
            shift ;;
        --values)
            [[ $# -ge 2 ]] || { err "--values requires a file path"; usage; exit 64; }
            VALUES_FILE="$2"
            shift 2 ;;
        --values=*)
            VALUES_FILE="${1#--values=}"
            shift ;;
        preflight|wizard|deploy|verify|doctor|reset)
            SUBCOMMAND="$1"
            shift
            break ;;
        --)
            shift
            break ;;
        -*)
            err "unknown flag: $1"
            usage
            exit 64 ;;
        *)
            err "unknown argument: $1"
            usage
            exit 64 ;;
    esac
done

# Allow flags AFTER a subcommand too (so `deploy --skip foo` is fine).
while (( $# )); do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --auto) export OBSERVIBELITY_AUTO=1; shift ;;
        --no-install) export OBSERVIBELITY_NO_INSTALL=1; shift ;;
        --no-fork) export OBSERVIBELITY_NO_FORK=1; shift ;;
        --no-atomic) export OBSERVIBELITY_NO_ATOMIC=1; shift ;;
        --system-install) export OBSERVIBELITY_SYSTEM_INSTALL=1; shift ;;
        --skip)
            [[ $# -ge 2 ]] || { err "--skip requires a phase name"; exit 64; }
            SKIPS+=("$2"); shift 2 ;;
        --skip=*) SKIPS+=("${1#--skip=}"); shift ;;
        --reset) DO_RESET=1; shift ;;
        --values)
            [[ $# -ge 2 ]] || { err "--values requires a file path"; exit 64; }
            VALUES_FILE="$2"; shift 2 ;;
        --values=*) VALUES_FILE="${1#--values=}"; shift ;;
        *)
            err "unexpected argument after subcommand: $1"
            usage
            exit 64 ;;
    esac
done

# Default values file.
VALUES_FILE="${VALUES_FILE:-$REPO_ROOT/.env}"

# ─── flag validation ─────────────────────────────────────────────────────────

# --auto requires a values file we can actually read (otherwise nothing to do).
if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" && ! -f "$VALUES_FILE" ]]; then
    die "--auto requires $VALUES_FILE; run wizard or copy .env.example to .env first"
fi

# ─── helpers ─────────────────────────────────────────────────────────────────

is_skipped() {
    local phase="$1" s
    for s in "${SKIPS[@]:-}"; do
        [[ "$s" == "$phase" ]] && return 0
    done
    return 1
}

source_values() {
    if [[ -f "$VALUES_FILE" ]]; then
        log "loading values from $VALUES_FILE"
        set -a
        # shellcheck disable=SC1090
        source "$VALUES_FILE"
        set +a
    fi
}

mark_phase_passed() {
    local phase="$1"
    state_set "phase_passed.${phase}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

run_doctor_collect() {
    local doctor="$REPO_ROOT/tools/deploy-doctor.sh"
    if [[ ! -x "$doctor" ]]; then
        # Phase 0: deploy-doctor.sh may not exist yet; check providers dir layout.
        doctor="$REPO_ROOT/tools/deploy-doctor/main.sh"
    fi
    if [[ -x "$doctor" ]]; then
        warn "running deploy-doctor --collect-only to capture diagnostics"
        local out
        if out=$("$doctor" --collect-only 2>&1); then
            local tarball
            tarball=$(printf '%s\n' "$out" | grep -Eo '/[^[:space:]]+\.tar(\.gz)?' | tail -n1 || true)
            if [[ -n "$tarball" ]]; then
                echo "$tarball"
                return 0
            fi
            # Fall through if we can't parse; still log the output.
            printf '%s\n' "$out" >&2
        else
            warn "deploy-doctor --collect-only failed; see output above"
        fi
    else
        warn "deploy-doctor not found at $doctor — skipping collection"
    fi
    return 1
}

# ─── phase runners ───────────────────────────────────────────────────────────

run_preflight() {
    if is_skipped preflight; then
        step "preflight" "skipped via --skip"
        return 0
    fi
    step "preflight" "running preflight checks"
    local main="$REPO_ROOT/tools/preflight/main.sh"
    if [[ ! -x "$main" ]]; then
        if [[ -f "$main" ]]; then
            bash "$main" || return 1
        else
            die "preflight orchestrator not found at $main"
        fi
    else
        "$main" || return 1
    fi
    mark_phase_passed preflight
    ok "preflight passed"
}

run_wizard() {
    if is_skipped wizard; then
        step "wizard" "skipped via --skip"
        return 0
    fi
    step "wizard" "gathering deployment inputs"
    local wiz="$REPO_ROOT/tools/wizard.sh"
    [[ -e "$wiz" ]] || die "wizard not found at $wiz"
    if [[ -x "$wiz" ]]; then
        "$wiz" || return $?
    else
        bash "$wiz" || return $?
    fi
    mark_phase_passed wizard
    ok "wizard complete"
}

run_deploy() {
    if is_skipped deploy; then
        step "deploy" "skipped via --skip"
        return 0
    fi
    step "deploy" "Running helm upgrade --install"

    local extra_values=()
    if [[ "$(kubectl config current-context 2>/dev/null)" == "docker-desktop" ]] \
       && [[ -f "$REPO_ROOT/values-docker-desktop.yaml" ]]; then
        extra_values+=(-f "$REPO_ROOT/values-docker-desktop.yaml")
        log "Detected docker-desktop context; including values-docker-desktop.yaml"
    fi

    local atomic_flag="--atomic"
    if [[ "${OBSERVIBELITY_NO_ATOMIC:-}" == "1" ]]; then
        atomic_flag=""
        warn "Atomic deploy disabled (OBSERVIBELITY_NO_ATOMIC=1); failed deploys won't auto-rollback"
    fi

    local values_args=()
    if [[ -f "$REPO_ROOT/.env" ]]; then
        values_args+=(-f "$REPO_ROOT/.env")
    fi

    if ! helm upgrade --install "${HELM_RELEASE:-observibelity}" "$REPO_ROOT" \
         --namespace "${HELM_NAMESPACE:-observibelity}" \
         --create-namespace \
         "${values_args[@]}" \
         "${extra_values[@]}" \
         $atomic_flag \
         --wait \
         --timeout "${HELM_TIMEOUT:-5m}"; then
        err "helm upgrade failed"
        return 3
    fi

    state_mark_passed deploy
    ok "deploy complete (release: ${HELM_RELEASE:-observibelity}, namespace: ${HELM_NAMESPACE:-observibelity})"
    log "Run 'make verify' or './install.sh verify' to check health"
    return 0
}

run_verify() {
    if is_skipped verify; then
        step "verify" "skipped via --skip"
        return 0
    fi
    step "verify" "verifying deployed/scaffolded state"
    local v="$REPO_ROOT/tools/verify.sh"
    if [[ -x "$v" ]]; then
        "$v" || return 1
    elif [[ -f "$v" ]]; then
        bash "$v" || return 1
    else
        warn "verify.sh not found at $v (Phase 0 stub) — treating as pass"
    fi
    mark_phase_passed verify
    ok "verify passed"
}

run_doctor() {
    step "doctor" "running deploy-doctor"
    local doctor="$REPO_ROOT/tools/deploy-doctor.sh"
    if [[ ! -x "$doctor" ]]; then
        doctor="$REPO_ROOT/tools/deploy-doctor/main.sh"
    fi
    if [[ -x "$doctor" ]]; then
        "$doctor" "$@" || return $?
    elif [[ -f "$doctor" ]]; then
        bash "$doctor" "$@" || return $?
    else
        die "deploy-doctor not found at $doctor"
    fi
}

run_reset() {
    step "reset" "clearing persisted state"
    state_reset
    ok "state cleared"
}

# ─── dispatch ────────────────────────────────────────────────────────────────

if (( DO_RESET )); then
    run_reset
fi

source_values

case "$SUBCOMMAND" in
    preflight)
        run_preflight || exit 1
        exit 0
        ;;
    wizard)
        run_wizard
        rc=$?
        if (( rc == 0 )); then exit 0; fi
        # wizard cancellation = exit 2; other errors propagate.
        if (( rc == 2 )); then exit 2; fi
        exit "$rc"
        ;;
    deploy)
        run_deploy || exit 3
        exit 0
        ;;
    verify)
        run_verify || exit 4
        exit 0
        ;;
    doctor)
        run_doctor || exit $?
        exit 0
        ;;
    reset)
        # Already ran above if --reset; if subcommand is reset, ensure it runs.
        (( DO_RESET )) || run_reset
        exit 0
        ;;
    "")
        # All-in-one flow. Phases ≥ deploy trigger deploy-doctor on failure.
        log "ObserVIBElity — running full install flow (preflight → wizard → deploy → verify)"

        if ! run_preflight; then
            err "preflight failed"
            exit 1
        fi

        if ! run_wizard; then
            rc=$?
            err "wizard failed (exit $rc)"
            (( rc == 2 )) && exit 2
            exit "$rc"
        fi

        if ! run_deploy; then
            err "deploy failed"
            tarball=$(run_doctor_collect || true)
            if [[ -n "${tarball:-}" ]]; then
                err "deploy-doctor wrote ${tarball}; attach to a GitHub issue"
            else
                err "deploy-doctor recommended; run \`./install.sh doctor\` to collect diagnostics"
            fi
            exit 5
        fi

        if ! run_verify; then
            err "verify failed"
            tarball=$(run_doctor_collect || true)
            if [[ -n "${tarball:-}" ]]; then
                err "deploy-doctor wrote ${tarball}; attach to a GitHub issue"
            else
                err "deploy-doctor recommended; run \`./install.sh doctor\` to collect diagnostics"
            fi
            exit 5
        fi

        ok "Done."
        echo "Run \`./install.sh verify\` anytime to recheck health."
        echo "Read docs/ARCHITECTURE.md to learn what was deployed."
        exit 0
        ;;
    *)
        err "unknown subcommand: $SUBCOMMAND"
        usage
        exit 64
        ;;
esac
