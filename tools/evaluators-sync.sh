#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"
source "$REPO_ROOT/tools/lib/state.sh"

# evaluators-sync.sh — stub for syncing Grafana Sigil AI Observability
# evaluators from git ($REPO_ROOT/registry/evaluators/*.yaml) into Grafana
# Cloud.
#
# Phase 0: no API calls. Prints manual-workflow guidance. Real
# implementation lands in Phase 2 once Grafana's gcx CLI supports
# AI Observability evaluators.
#
# The subcommand shape (status / push / pull / diff) is locked in here so
# callers, docs, and CI can be written against it before Phase 2 lands.

EVALUATORS_DIR="$REPO_ROOT/registry/evaluators"

usage() {
  log "Usage: evaluators-sync.sh <subcommand>"
  log ""
  log "Subcommands:"
  log "  status   show local vs remote evaluator state"
  log "  push     apply local evaluators → Grafana Cloud"
  log "  pull     fetch remote evaluators → local files"
  log "  diff     show local vs remote diff"
  log ""
  log "  -h, --help   show this help"
}

# phase0_message <subcommand> — the shared Phase 0 notice. Every
# subcommand emits this and exits 0. When Phase 2 arrives, individual
# subcommands will replace this with real behaviour.
phase0_message() {
  local subcmd="$1"
  step "evaluators-sync $subcmd" "Phase 0 stub"
  log "Grafana's gcx CLI does not yet support AI Observability evaluators."
  log "For now, create evaluators manually in the Grafana Cloud UI."
  log "Reference: https://claude.wombatwags.com/planner/ai-o11y/#evaluators"
  log "This script will gain real functionality in Phase 2."
  exit 0
}

cmd_status() {
  # Even in Phase 0, surface a count of local evaluator files so a user
  # running `status` can sanity-check their checkout. Phase 0 will report
  # zero — registry/evaluators/ does not yet exist.
  local count=0
  if [[ -d "$EVALUATORS_DIR" ]]; then
    # shellcheck disable=SC2012  # ls -1 is fine for a count; we control the dir
    count=$(find "$EVALUATORS_DIR" -maxdepth 1 -type f -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ')
  fi
  log "$count evaluator files found in $EVALUATORS_DIR"
  log "manual check in UI; tooling lands in Phase 2"
  phase0_message "status"
}

cmd_push() {
  log "Not yet implemented. Create evaluators manually in Grafana Cloud UI."
  log "See docs/EVALUATORS.md (coming Phase 2)."
  phase0_message "push"
}

cmd_pull() {
  log "Not yet implemented. Create evaluators manually in Grafana Cloud UI."
  log "See docs/EVALUATORS.md (coming Phase 2)."
  phase0_message "pull"
}

cmd_diff() {
  log "Not yet implemented. Create evaluators manually in Grafana Cloud UI."
  log "See docs/EVALUATORS.md (coming Phase 2)."
  phase0_message "diff"
}

# --- dispatch ---------------------------------------------------------------

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

case "$1" in
  status)       shift; cmd_status   "$@" ;;
  push)         shift; cmd_push     "$@" ;;
  pull)         shift; cmd_pull     "$@" ;;
  diff)         shift; cmd_diff     "$@" ;;
  -h|--help)    usage; exit 0 ;;
  *)            die "unknown subcommand: $1 (try --help)" ;;
esac
