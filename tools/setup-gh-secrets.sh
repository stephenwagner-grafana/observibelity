#!/usr/bin/env bash
# setup-gh-secrets.sh — interactively set GH Actions secrets for ObserVIBElity.
#
# After `gh repo create`, run this once to populate the secrets that the
# e2e-smoke + integration workflows need. Reads values from .env if present
# (so you don't have to paste twice). Falls back to interactive prompts.
#
# Usage:
#   ./tools/setup-gh-secrets.sh                  # prompts (or reads .env)
#   ./tools/setup-gh-secrets.sh --from-env .env  # source from a file
#   ./tools/setup-gh-secrets.sh --check          # show which are set / missing

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"
source "$REPO_ROOT/tools/lib/prompt.sh"

ENV_FILE="$REPO_ROOT/.env"
MODE="set"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-env) ENV_FILE="$2"; shift 2 ;;
    --check) MODE="check"; shift ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--from-env FILE] [--check]
Sets these GH Actions secrets on the current gh-cli context's repo:
  ANTHROPIC_API_KEY
  GRAFANA_CLOUD_INSTANCE_ID
  GRAFANA_CLOUD_API_TOKEN
  GRAFANA_CLOUD_OTLP_ENDPOINT
  GRAFANA_URL
  OLLAMA_BASE_URL (optional)
EOF
      exit 0 ;;
    *) die "Unknown flag: $1" ;;
  esac
done

command -v gh >/dev/null || die "gh CLI not installed; brew install gh / apt install gh"
gh auth status >/dev/null 2>&1 || die "gh not authenticated; run: gh auth login"

REQUIRED=(ANTHROPIC_API_KEY GRAFANA_CLOUD_INSTANCE_ID GRAFANA_CLOUD_API_TOKEN GRAFANA_CLOUD_OTLP_ENDPOINT GRAFANA_URL)
OPTIONAL=(OLLAMA_BASE_URL)

if [[ "$MODE" == "check" ]]; then
  step "check" "Current GH Actions secrets"
  existing=$(gh secret list --json name -q '.[].name' 2>/dev/null || echo "")
  for s in "${REQUIRED[@]}"; do
    if echo "$existing" | grep -qx "$s"; then ok "  $s"; else err "  $s (missing)"; fi
  done
  for s in "${OPTIONAL[@]}"; do
    if echo "$existing" | grep -qx "$s"; then ok "  $s (optional)"; else warn "  $s (optional, not set)"; fi
  done
  exit 0
fi

# Load from .env if present so we don't ask for what we already have
if [[ -f "$ENV_FILE" ]]; then
  log "Reading defaults from $ENV_FILE"
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

set_secret() {
  local name="$1" current_val="${!1:-}" optional="${2:-}"
  if [[ -n "$current_val" ]]; then
    log "  $name = (loaded from .env)"
  elif [[ "$optional" == "optional" ]]; then
    current_val=$(ask "  $name (optional, blank to skip)" "")
    [[ -z "$current_val" ]] && return 0
  else
    current_val=$(ask_secret "  $name")
    [[ -z "$current_val" ]] && die "$name is required"
  fi
  echo "$current_val" | gh secret set "$name" --body - >/dev/null
  ok "  set $name"
}

step "secrets" "Uploading to gh secrets"
for s in "${REQUIRED[@]}"; do set_secret "$s"; done
for s in "${OPTIONAL[@]}"; do set_secret "$s" optional; done

ok "Done. Run: gh workflow list / gh run watch to confirm CI starts passing."
