#!/usr/bin/env bash
# Validate every credential ObserVIBElity needs with a *live* API call.
#
# We do not store raw credentials in state — only a sha256 hash so a later
# re-run can detect "the value changed since last check". `$1` (optional)
# overrides the path to the .env file, defaulting to $REPO_ROOT/.env.
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

state_init

ENV_FILE="${1:-$REPO_ROOT/.env}"
if [[ -f "$ENV_FILE" ]]; then
    log "Loading credentials from $ENV_FILE"
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a
else
    warn "No .env file at $ENV_FILE — relying on environment."
fi

AUTO="${OBSERVIBELITY_AUTO:-}"
NOW="$(date -Iseconds)"

declare -a MISSING=()      # required-but-unset
declare -a INVALID=()      # set but live call failed

# sha256 of a string without surrounding whitespace.
sha256_of() {
    printf '%s' "$1" | sha256sum | cut -d' ' -f1
}

# Record validation result for a credential in state.
mark_cred() {
    local name="$1" value="$2" validated="$3"
    local hash
    hash="$(sha256_of "$value")"
    state_set "preflight.creds.${name}.hash"       "$hash"
    state_set "preflight.creds.${name}.validated" "$validated"
    state_set "preflight.creds.${name}.last_check" "$NOW"
}

# Wrap "this required cred is unset" handling so each credential block stays
# small. Honors OBSERVIBELITY_AUTO=1 → hard fail; otherwise warn and leave for
# the wizard.
handle_missing_required() {
    local name="$1"
    if [[ "$AUTO" == "1" ]]; then
        err "$name not set (OBSERVIBELITY_AUTO=1 — refusing to prompt)"
        MISSING+=("$name")
    else
        warn "$name not set — the wizard will collect it."
        MISSING+=("$name")
    fi
}

# ---------------------------------------------------------------------------
# ANTHROPIC_API_KEY (required)
# ---------------------------------------------------------------------------
step "check-credentials" "ANTHROPIC_API_KEY"
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    handle_missing_required "ANTHROPIC_API_KEY"
else
    code="$(curl -sS -o /dev/null -w "%{http_code}" \
        --max-time 15 \
        https://api.anthropic.com/v1/models \
        -H "x-api-key: $ANTHROPIC_API_KEY" \
        -H "anthropic-version: 2023-06-01" \
        || echo "000")"
    if [[ "$code" == "200" ]]; then
        ok "Anthropic API key validated (200)."
        mark_cred "ANTHROPIC_API_KEY" "$ANTHROPIC_API_KEY" "true"
    else
        err "Anthropic API returned HTTP $code (expected 200)."
        mark_cred "ANTHROPIC_API_KEY" "$ANTHROPIC_API_KEY" "false"
        INVALID+=("ANTHROPIC_API_KEY")
    fi
fi

# ---------------------------------------------------------------------------
# Grafana Cloud OTLP triple (required)
# ---------------------------------------------------------------------------
step "check-credentials" "GRAFANA_CLOUD_OTLP_*"
if [[ -z "${GRAFANA_CLOUD_OTLP_ENDPOINT:-}" || -z "${GRAFANA_CLOUD_INSTANCE_ID:-}" || -z "${GRAFANA_CLOUD_API_TOKEN:-}" ]]; then
    for n in GRAFANA_CLOUD_OTLP_ENDPOINT GRAFANA_CLOUD_INSTANCE_ID GRAFANA_CLOUD_API_TOKEN; do
        if [[ -z "${!n:-}" ]]; then handle_missing_required "$n"; fi
    done
else
    code="$(curl -sS -o /dev/null -w "%{http_code}" \
        --max-time 15 \
        -I \
        -u "${GRAFANA_CLOUD_INSTANCE_ID}:${GRAFANA_CLOUD_API_TOKEN}" \
        "$GRAFANA_CLOUD_OTLP_ENDPOINT" \
        || echo "000")"
    case "$code" in
        200|202|405)
            ok "Grafana Cloud OTLP endpoint reachable (HTTP $code)."
            # Hash a composite of all three so a change to any one is detected.
            triple="${GRAFANA_CLOUD_OTLP_ENDPOINT}|${GRAFANA_CLOUD_INSTANCE_ID}|${GRAFANA_CLOUD_API_TOKEN}"
            mark_cred "GRAFANA_CLOUD_OTLP" "$triple" "true"
            ;;
        *)
            err "Grafana Cloud OTLP endpoint returned HTTP $code (expected 200/202/405)."
            triple="${GRAFANA_CLOUD_OTLP_ENDPOINT}|${GRAFANA_CLOUD_INSTANCE_ID}|${GRAFANA_CLOUD_API_TOKEN}"
            mark_cred "GRAFANA_CLOUD_OTLP" "$triple" "false"
            INVALID+=("GRAFANA_CLOUD_OTLP")
            ;;
    esac
fi

# ---------------------------------------------------------------------------
# GITHUB_TOKEN (required unless OBSERVIBELITY_NO_FORK=1)
# ---------------------------------------------------------------------------
step "check-credentials" "GITHUB_TOKEN"
if [[ "${OBSERVIBELITY_NO_FORK:-}" == "1" ]]; then
    log "OBSERVIBELITY_NO_FORK=1 — skipping GitHub token check."
elif [[ -z "${GITHUB_TOKEN:-}" ]]; then
    handle_missing_required "GITHUB_TOKEN"
else
    # We need both body+headers; capture them separately.
    tmp_hdr="$(mktemp)"
    tmp_body="$(mktemp)"
    trap 'rm -f "$tmp_hdr" "$tmp_body"' EXIT
    code="$(curl -sS \
        -o "$tmp_body" \
        -D "$tmp_hdr" \
        -w "%{http_code}" \
        --max-time 15 \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        https://api.github.com/user \
        || echo "000")"
    if [[ "$code" != "200" ]]; then
        err "GitHub API returned HTTP $code (expected 200)."
        mark_cred "GITHUB_TOKEN" "$GITHUB_TOKEN" "false"
        INVALID+=("GITHUB_TOKEN")
    else
        # x-oauth-scopes header is comma-separated. We need "repo".
        scopes="$(grep -i '^x-oauth-scopes:' "$tmp_hdr" | sed 's/^[Xx]-[Oo][Aa]uth-[Ss]copes:[[:space:]]*//' | tr -d '\r')"
        log "GitHub token scopes: ${scopes:-<none>}"
        if grep -qiw "repo" <<< "$scopes"; then
            ok "GitHub token has 'repo' scope."
            mark_cred "GITHUB_TOKEN" "$GITHUB_TOKEN" "true"
        else
            err "GitHub token is missing the 'repo' scope (got: ${scopes:-none})."
            mark_cred "GITHUB_TOKEN" "$GITHUB_TOKEN" "false"
            INVALID+=("GITHUB_TOKEN")
        fi
    fi
fi

# ---------------------------------------------------------------------------
# OLLAMA_BASE_URL (optional — only check if user set it)
# ---------------------------------------------------------------------------
step "check-credentials" "OLLAMA_BASE_URL"
if [[ -z "${OLLAMA_BASE_URL:-}" ]]; then
    log "OLLAMA_BASE_URL not set — skipping."
else
    code="$(curl -sS -o /dev/null -w "%{http_code}" \
        --max-time 15 \
        "${OLLAMA_BASE_URL%/}/api/tags" \
        || echo "000")"
    if [[ "$code" == "200" ]]; then
        ok "Ollama endpoint reachable (200)."
        mark_cred "OLLAMA_BASE_URL" "$OLLAMA_BASE_URL" "true"
    else
        err "Ollama endpoint returned HTTP $code (expected 200)."
        mark_cred "OLLAMA_BASE_URL" "$OLLAMA_BASE_URL" "false"
        INVALID+=("OLLAMA_BASE_URL")
    fi
fi

# ---------------------------------------------------------------------------
# Verdict.
# ---------------------------------------------------------------------------
if [[ "${#INVALID[@]}" -gt 0 ]]; then
    err "Invalid credentials: ${INVALID[*]}"
    exit 1
fi

if [[ "${#MISSING[@]}" -gt 0 ]]; then
    if [[ "$AUTO" == "1" ]]; then
        err "Missing required credentials in non-interactive mode: ${MISSING[*]}"
        exit 1
    fi
    warn "Missing required credentials will be collected by the wizard: ${MISSING[*]}"
    # Per spec: don't fail if interactive — the wizard runs next.
fi

ok "Credential check complete."
exit 0
