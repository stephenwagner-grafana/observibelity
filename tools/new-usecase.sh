#!/usr/bin/env bash
#
# ObserVIBElity — interactive new-use-case wizard.
#
# Walks the author through the questions needed to scaffold a bundled use case
# YAML at registry/use_cases/<name>.yaml. The output is consumed by the
# compiler at tools/usecase-build.sh, which fans the bundle out into
# Sigil/Grafana/loadgen artifacts under registry/_generated/.
#
# Sibling surface: .claude/skills/add-use-case/SKILL.md (Claude Code skill).
#
# Reference:
#   - docs/USE-CASES.md          authoring guide
#   - tools/usecase_build/schema.py     Pydantic source of truth
#   - tools/usecase-templates/<arch>/   per-archetype template packs
#
# Exit codes:
#   0   YAML written
#   1   validation / IO error
#   2   user aborted

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tools/lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"
# shellcheck source=tools/lib/prompt.sh
source "$REPO_ROOT/tools/lib/prompt.sh"

step "new-usecase" "Interactive use case wizard"
log "This wizard creates a bundled use-case YAML at registry/use_cases/<name>.yaml"
log "Reference: docs/USE-CASES.md"
echo ""

# ─── 1. name (kebab-case) ────────────────────────────────────────────────────
NAME="$(ask "Use case name (kebab-case, e.g. data-theft-tim)" "")"
[[ -n "$NAME" ]] || die "Name is required"
if [[ ! "$NAME" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
    die "Name must be lowercase, alphanumeric, hyphens/underscores allowed. Got: $NAME"
fi

OUTPUT="$REPO_ROOT/registry/use_cases/$NAME.yaml"
if [[ -e "$OUTPUT" ]]; then
    ask_yn "$OUTPUT already exists. Overwrite?" N || die "Aborted"
fi

# ─── 2. title (human-readable) ───────────────────────────────────────────────
DEFAULT_TITLE="$(echo "$NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++)$i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')"
TITLE="$(ask "Title (human-readable)" "$DEFAULT_TITLE")"

# ─── 3. app ──────────────────────────────────────────────────────────────────
APP_CHOICE=$(ask_choice "Which app does this use case apply to?" "NeonCart" "Support Bot" "Both")
case "$APP_CHOICE" in
    1) APP="neoncart" ;;
    2) APP="supportbot" ;;
    3) APP="both" ;;
esac

# ─── 4. phase ────────────────────────────────────────────────────────────────
PHASE=$(ask_choice "Phase" "Phase 1 (mice-rca milestone)" "Phase 2 (full set)")
case "$PHASE" in
    1) PHASE_NUM=1 ;;
    2) PHASE_NUM=2 ;;
esac

# ─── 5. archetype — the key choice ───────────────────────────────────────────
log ""
log "Archetypes (pick the one your use case most resembles):"
log "  1. trace-and-fix         — One trace ID, one error span, one fix (mice-RCA pattern)"
log "  2. per-user-pattern      — Sticky persona repeats; leaderboard surfaces them (Tim, Mara, Jordan)"
log "  3. leaderboard           — Rate/count ranked across categories (Model Winner, Brand Voice)"
log "  4. single-event-severity — ANY critical event fires alert (PII echo, hiring-discrim)"
log "  5. cascade               — Counter > N per session/minute (Email Cascade, Token Spikes)"
ARCH_CHOICE=$(ask_choice "Archetype" "trace-and-fix" "per-user-pattern" "leaderboard" "single-event-severity" "cascade")
case "$ARCH_CHOICE" in
    1) ARCHETYPE="trace-and-fix" ;;
    2) ARCHETYPE="per-user-pattern" ;;
    3) ARCHETYPE="leaderboard" ;;
    4) ARCHETYPE="single-event-severity" ;;
    5) ARCHETYPE="cascade" ;;
esac

# ─── 6. centerpiece flag ─────────────────────────────────────────────────────
if ask_yn "Is this a centerpiece use case? (requires SLO + evaluators)" N; then
    CENTERPIECE="true"
else
    CENTERPIECE="false"
fi

# ─── 7. archetype README hints ───────────────────────────────────────────────
ARCHETYPE_README="$REPO_ROOT/tools/usecase-templates/$ARCHETYPE/README.md"
if [[ -f "$ARCHETYPE_README" ]]; then
    log ""
    log "Archetype README:"
    log "---"
    cat "$ARCHETYPE_README" >&2
    log "---"
else
    log ""
    warn "Archetype README not found: $ARCHETYPE_README"
    log "Proceeding anyway — fill in evaluator + alert manually after generation."
fi

# ─── 8. description ──────────────────────────────────────────────────────────
DESCRIPTION="$(ask "One-paragraph description" "")"

# ─── 9. persona (conditional on archetype) ───────────────────────────────────
PERSONA=""
if [[ "$ARCHETYPE" == "per-user-pattern" ]] || [[ "$ARCHETYPE" == "cascade" ]]; then
    PERSONA="$(ask "Persona ID for the pattern (e.g. u-tim-l)" "u-${NAME}-l")"
fi

# ─── 10. severity ────────────────────────────────────────────────────────────
SEVERITY=$(ask_choice "Default severity" "low" "medium" "high" "critical")
case "$SEVERITY" in
    1) SEV="low" ;;
    2) SEV="medium" ;;
    3) SEV="high" ;;
    4) SEV="critical" ;;
esac

# ─── 11. SLO (if centerpiece) ────────────────────────────────────────────────
SLO_SECTION=""
if [[ "$CENTERPIECE" == "true" ]]; then
    SLO_OBJ="$(ask "SLO objective (e.g. '0 exfil events per day')" "")"
    SLO_SECTION="
slo:
  objective: \"$SLO_OBJ\"
  error_budget: 0.001
  window: 30d"
fi

# ─── 12. demo "How to sell" ──────────────────────────────────────────────────
SELL="$(ask "One-line sales pitch (How to sell)" "$TITLE")"

# ─── 13. archetype-driven template keys ──────────────────────────────────────
case "$ARCHETYPE" in
    trace-and-fix)         K6_TEMPLATE="trigger-and-error";  PANELS_TEMPLATE="trace-and-error" ;;
    per-user-pattern)      K6_TEMPLATE="sticky-persona";     PANELS_TEMPLATE="per-user-leaderboard" ;;
    leaderboard)           K6_TEMPLATE="baseline-rate";      PANELS_TEMPLATE="category-leaderboard" ;;
    single-event-severity) K6_TEMPLATE="rare-critical";      PANELS_TEMPLATE="critical-event-stream" ;;
    cascade)               K6_TEMPLATE="session-cascade";    PANELS_TEMPLATE="session-cascade" ;;
esac

# Underscore-version of name for identifiers that can't contain hyphens.
NAME_UND="${NAME//-/_}"
# Dot-version for evaluator / alert namespacing.
NAME_DOT="${NAME//-/.}"

# Conditional persona line (skip if empty so YAML stays clean).
PERSONA_LINE=""
if [[ -n "$PERSONA" ]]; then
    PERSONA_LINE="
    persona: $PERSONA"
fi

# ─── 14. write the YAML ──────────────────────────────────────────────────────
mkdir -p "$(dirname "$OUTPUT")"
cat > "$OUTPUT" <<EOF
# Use case: $TITLE
# Created by tools/new-usecase.sh on $(date -Iseconds)

name: $NAME
title: "$TITLE"
app: $APP
phase: $PHASE_NUM
centerpiece: $CENTERPIECE
archetype: $ARCHETYPE
description: |
  $DESCRIPTION

scenarios:
  - name: ${NAME_UND}_main
    k6_template: $K6_TEMPLATE${PERSONA_LINE}
    weight: 4
    rate: "5m"
    params: {}

evaluators:
  - name: ${NAME_DOT}.pattern_detected
    kind: rule
    severity: $SEV
    spec: |
      # TODO: write Sigil rule expression here.
      # Reference: gen_ai.* + ai_o11y.* OTel attributes
      # See planner § 05 Evaluators for examples.
      tbd

dashboard:
  uid: ai-obs-$NAME
  title: "$TITLE"
  panels_from_template: $PANELS_TEMPLATE
  extra_panels: []

alerts:
  - name: ${NAME_DOT}.detection
    condition: |
      # TODO: write PromQL expression
      rate(${NAME_UND}_event_total[5m]) > 0
    severity: $SEV
    duration: 5m
$SLO_SECTION

demo:
  do: "Wait ≥5m for loadgen (persona-driven) OR manually trigger via UI"
  signal: "${NAME_UND}_event with severity=$SEV; alert: name=${NAME_DOT}.detection state=firing"
  sell: "$SELL"
EOF

ok "Wrote $OUTPUT"
log ""
log "Next steps:"
log "  1. \$EDITOR $OUTPUT             # fill in evaluator spec + alert condition"
log "  2. make build-usecases          # compile → derived artifacts in registry/_generated/"
log "  3. make dev                     # deploy"
log "  4. make verify                  # confirm"
