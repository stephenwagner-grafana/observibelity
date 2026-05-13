#!/usr/bin/env bash
#
# ObserVIBElity — interactive wizard.
#
# Walks the user through every input the installer needs, validates them, then
# writes a `.env` file (mode 0600) at the repo root.
#
# Re-running the wizard reads existing values from .env and offers them as
# defaults so partial setup is easy to resume.
#
# Honors OBSERVIBELITY_AUTO=1 for non-interactive runs (validates whatever's
# already in env, dies if anything required is missing).
#
# Honors OBSERVIBELITY_NO_FORK=1 to skip the GitHub PAT prompt.
#
# Exit codes:
#   0 wizard complete; .env written
#   2 user cancelled or input was invalid

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT

LIB_DIR="$REPO_ROOT/tools/lib"
for lib in colors logging state prompt os; do
    f="$LIB_DIR/${lib}.sh"
    if [[ -f "$f" ]]; then
        # shellcheck disable=SC1090
        source "$f"
    fi
done

state_init 2>/dev/null || true

ENV_FILE="$REPO_ROOT/.env"

# ─── pre-load existing .env as defaults ──────────────────────────────────────

if [[ -f "$ENV_FILE" ]]; then
    log "found existing .env — using current values as defaults"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# ─── helpers ─────────────────────────────────────────────────────────────────

mask_value() {
    local v="$1"
    if [[ -z "$v" ]]; then
        printf '(unset)'
    elif (( ${#v} <= 4 )); then
        printf '***'
    else
        printf '%s***' "${v:0:4}"
    fi
}

# Read with a default value, displaying the default in the prompt.
read_with_default() {
    local prompt="$1" default="${2:-}" varname="$3" answer
    if [[ -n "$default" ]]; then
        answer=$(ask "${prompt} [${default}]: ")
        answer="${answer:-$default}"
    else
        answer=$(ask "${prompt}: ")
    fi
    printf -v "$varname" '%s' "$answer"
}

# Open a URL in the user's default browser (best-effort, never fatal).
open_url() {
    local url="$1"
    if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]]; then
        log "browser link (auto mode, not opened): $url"
        return 0
    fi
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 &
    elif command -v start >/dev/null 2>&1; then
        start "$url" >/dev/null 2>&1 &
    else
        log "open this URL in your browser: $url"
    fi
}

# Validate numeric (digits only).
is_numeric() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

# ─── step 1: apps to deploy ──────────────────────────────────────────────────

step "apps" "Which apps to deploy?"
echo "  Available in Phase 0:"
echo "    1) NeonCart"
echo "    -) Support Bot (Phase 2)   [grey — not yet available]"
APPS="${APPS:-neoncart}"
# Only one real choice in Phase 0; ask_choice keeps the UX consistent.
APPS=$(ask_choice "Pick apps" "neoncart" "neoncart")
log "selected apps: $APPS"

# ─── step 2: Anthropic API key ───────────────────────────────────────────────

step "anthropic" "Anthropic API key"
echo "  Sign-up / key console: https://console.anthropic.com/settings/keys"
if [[ "${OBSERVIBELITY_AUTO:-0}" != "1" ]]; then
    if ask_yn "Open the Anthropic console in your browser?" Y; then
        open_url "https://console.anthropic.com/settings/keys"
    fi
fi
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    log "current value: $(mask_value "$ANTHROPIC_API_KEY")"
    if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]] || ask_yn "Keep existing key?" Y; then
        :
    else
        ANTHROPIC_API_KEY=$(ask_secret "Paste your Anthropic API key:")
    fi
else
    ANTHROPIC_API_KEY=$(ask_secret "Paste your Anthropic API key:")
fi
[[ -n "$ANTHROPIC_API_KEY" ]] || die "ANTHROPIC_API_KEY is required"

# ─── step 3: Grafana Cloud ───────────────────────────────────────────────────

step "grafana-cloud" "Grafana Cloud credentials"
echo "  Free signup: https://grafana.com/auth/sign-up/create-user"
if [[ "${OBSERVIBELITY_AUTO:-0}" != "1" ]]; then
    if ask_yn "Open Grafana Cloud signup?" N; then
        open_url "https://grafana.com/auth/sign-up/create-user"
    fi
fi

# Instance ID (numeric).
while true; do
    read_with_default "Grafana Cloud Instance ID (numeric, e.g. 1234567)" \
        "${GRAFANA_CLOUD_INSTANCE_ID:-}" GRAFANA_CLOUD_INSTANCE_ID
    if [[ -z "$GRAFANA_CLOUD_INSTANCE_ID" ]]; then
        warn "Instance ID is required"
        continue
    fi
    if ! is_numeric "$GRAFANA_CLOUD_INSTANCE_ID"; then
        warn "Instance ID must be numeric (got: $GRAFANA_CLOUD_INSTANCE_ID)"
        continue
    fi
    break
done

# API token (Cloud Access Policy).
if [[ -n "${GRAFANA_CLOUD_API_TOKEN:-}" ]]; then
    log "current token: $(mask_value "$GRAFANA_CLOUD_API_TOKEN")"
    if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]] || ask_yn "Keep existing Cloud Access Policy token?" Y; then
        :
    else
        GRAFANA_CLOUD_API_TOKEN=$(ask_secret "Paste Cloud Access Policy token:")
    fi
else
    GRAFANA_CLOUD_API_TOKEN=$(ask_secret "Paste Cloud Access Policy token:")
fi
[[ -n "$GRAFANA_CLOUD_API_TOKEN" ]] || die "GRAFANA_CLOUD_API_TOKEN is required"

# OTLP endpoint by region.
REGION_DEFAULT="${GRAFANA_CLOUD_REGION:-us-east}"
GRAFANA_CLOUD_REGION=$(ask_choice "Grafana Cloud region" \
    "$REGION_DEFAULT" \
    "us-east" "us-central" "eu-west" "ap-southeast")
GRAFANA_CLOUD_OTLP_ENDPOINT="https://otlp-gateway-prod-${GRAFANA_CLOUD_REGION}-0.grafana.net/otlp"
log "OTLP endpoint: ${GRAFANA_CLOUD_OTLP_ENDPOINT}"

# ─── step 4: GitHub PAT ──────────────────────────────────────────────────────

if [[ "${OBSERVIBELITY_NO_FORK:-0}" == "1" ]]; then
    log "skipping GitHub fork (OBSERVIBELITY_NO_FORK=1)"
    GITHUB_TOKEN="${GITHUB_TOKEN:-}"
    GITHUB_ORG="${GITHUB_ORG:-}"
else
    step "github" "GitHub Personal Access Token (for forking the repo)"
    echo "  Create one with scope=repo: https://github.com/settings/tokens/new?scopes=repo"
    if [[ "${OBSERVIBELITY_AUTO:-0}" != "1" ]]; then
        if ask_yn "Open the GitHub token-create page?" N; then
            open_url "https://github.com/settings/tokens/new?scopes=repo"
        fi
    fi
    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        log "current PAT: $(mask_value "$GITHUB_TOKEN")"
        if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]] || ask_yn "Keep existing GitHub PAT?" Y; then
            :
        else
            GITHUB_TOKEN=$(ask_secret "Paste GitHub PAT:")
        fi
    else
        GITHUB_TOKEN=$(ask_secret "Paste GitHub PAT:")
    fi

    # GitHub org — try `gh auth status` to detect current user.
    GH_USER_DEFAULT="${GITHUB_ORG:-}"
    if [[ -z "$GH_USER_DEFAULT" ]] && command -v gh >/dev/null 2>&1; then
        GH_USER_DEFAULT="$(gh api user --jq .login 2>/dev/null || true)"
    fi
    read_with_default "GitHub org to fork into" "$GH_USER_DEFAULT" GITHUB_ORG
fi

# ─── step 5: Optional Ollama ─────────────────────────────────────────────────

step "ollama" "Optional Ollama host"
USE_OLLAMA_DEFAULT="N"
[[ -n "${OLLAMA_BASE_URL:-}" ]] && USE_OLLAMA_DEFAULT="Y"
if ask_yn "Configure an external Ollama endpoint?" "$USE_OLLAMA_DEFAULT"; then
    read_with_default "Ollama base URL (e.g. http://192.168.1.50:11434)" \
        "${OLLAMA_BASE_URL:-}" OLLAMA_BASE_URL
else
    OLLAMA_BASE_URL=""
fi

# ─── step 6: Ingress host for NeonCart ───────────────────────────────────────

step "ingress" "Ingress host for NeonCart"
KCTX="$(kubectl config current-context 2>/dev/null || echo "")"
case "$KCTX" in
    *k3d*|*docker-desktop*|"")
        INGRESS_DEFAULT="${INGRESS_HOST_NEONCART:-neoncart.localhost}"
        ;;
    *)
        INGRESS_DEFAULT="${INGRESS_HOST_NEONCART:-neoncart.example.com}"
        ;;
esac
read_with_default "Ingress hostname for NeonCart" "$INGRESS_DEFAULT" INGRESS_HOST_NEONCART

# ─── step 7: StorageClass ────────────────────────────────────────────────────

step "storage" "Kubernetes StorageClass"
if command -v kubectl >/dev/null 2>&1; then
    SCS=$(kubectl get storageclass --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null || true)
    if [[ -n "$SCS" ]]; then
        echo "  Available StorageClasses on this cluster:"
        echo "$SCS" | sed 's/^/    - /'
    else
        log "no StorageClasses returned by kubectl (or no cluster access)"
    fi
fi
read_with_default "StorageClass (empty = cluster default)" "${STORAGE_CLASS:-}" STORAGE_CLASS

# ─── validation: check credentials ──────────────────────────────────────────

step "validate" "validating credentials"
CRED_CHECK="$REPO_ROOT/tools/preflight/check-credentials.sh"
if [[ -x "$CRED_CHECK" ]]; then
    if ! ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
         GRAFANA_CLOUD_INSTANCE_ID="$GRAFANA_CLOUD_INSTANCE_ID" \
         GRAFANA_CLOUD_API_TOKEN="$GRAFANA_CLOUD_API_TOKEN" \
         GITHUB_TOKEN="${GITHUB_TOKEN:-}" \
         "$CRED_CHECK"; then
        warn "credential check failed (continuing — fix later if you must)"
    else
        ok "credentials validated"
    fi
elif [[ -f "$CRED_CHECK" ]]; then
    if ! bash "$CRED_CHECK"; then
        warn "credential check failed (continuing — fix later if you must)"
    else
        ok "credentials validated"
    fi
else
    warn "check-credentials.sh not found — skipping validation"
fi

# ─── summary ─────────────────────────────────────────────────────────────────

echo
log "Summary (secrets are masked):"
printf "  %-32s %s\n" "APPS"                         "$APPS"
printf "  %-32s %s\n" "ANTHROPIC_API_KEY"            "$(mask_value "$ANTHROPIC_API_KEY")"
printf "  %-32s %s\n" "GRAFANA_CLOUD_INSTANCE_ID"    "$GRAFANA_CLOUD_INSTANCE_ID"
printf "  %-32s %s\n" "GRAFANA_CLOUD_API_TOKEN"      "$(mask_value "$GRAFANA_CLOUD_API_TOKEN")"
printf "  %-32s %s\n" "GRAFANA_CLOUD_OTLP_ENDPOINT"  "$GRAFANA_CLOUD_OTLP_ENDPOINT"
printf "  %-32s %s\n" "GITHUB_TOKEN"                 "$(mask_value "${GITHUB_TOKEN:-}")"
printf "  %-32s %s\n" "GITHUB_ORG"                   "${GITHUB_ORG:-}"
printf "  %-32s %s\n" "OLLAMA_BASE_URL"              "${OLLAMA_BASE_URL:-(unset)}"
printf "  %-32s %s\n" "INGRESS_HOST_NEONCART"        "$INGRESS_HOST_NEONCART"
printf "  %-32s %s\n" "STORAGE_CLASS"                "${STORAGE_CLASS:-(cluster default)}"
echo

if ! ask_yn "Write to ${ENV_FILE} and proceed?" Y; then
    log "cancelled — nothing written"
    exit 2
fi

# ─── write .env ──────────────────────────────────────────────────────────────

umask 0077
cat >"$ENV_FILE" <<EOF
# ObserVIBElity .env — generated by tools/wizard.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Do NOT commit this file. mode 0600.

PHASE=0
APPS=${APPS}

# Anthropic
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

# Grafana Cloud
GRAFANA_CLOUD_INSTANCE_ID=${GRAFANA_CLOUD_INSTANCE_ID}
GRAFANA_CLOUD_API_TOKEN=${GRAFANA_CLOUD_API_TOKEN}
GRAFANA_CLOUD_REGION=${GRAFANA_CLOUD_REGION}
GRAFANA_CLOUD_OTLP_ENDPOINT=${GRAFANA_CLOUD_OTLP_ENDPOINT}

# GitHub (for forking the repo)
GITHUB_TOKEN=${GITHUB_TOKEN:-}
GITHUB_ORG=${GITHUB_ORG:-}

# Optional — external Ollama
OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-}

# Ingress
INGRESS_HOST_NEONCART=${INGRESS_HOST_NEONCART}

# Storage (empty = cluster default)
STORAGE_CLASS=${STORAGE_CLASS:-}
EOF
chmod 600 "$ENV_FILE"
ok "wrote ${ENV_FILE} (mode 0600)"

state_mark_passed wizard
exit 0
