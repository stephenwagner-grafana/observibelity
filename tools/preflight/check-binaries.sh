#!/usr/bin/env bash
# Verify the binaries ObserVIBElity needs are present and recent enough.
#
# For each required tool: if missing, offer to install into tools/bin/ via the
# os.sh pkg_install helper (or fail fast when OBSERVIBELITY_NO_INSTALL=1).
# For version checks we compare with `sort -V`; too-old versions warn but do
# not fail — older releases often still work in practice and we don't want
# preflight to become an artificial gate.
#
# Writes a JSON object to state.preflight.binaries describing every tool we
# inspected: { tool: { version, min, ok } }.
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

# Required tools: "<name>:<min-version-or-empty>". Empty min means "any".
REQUIRED=(
    "kubectl:1.27"
    "helm:3.13"
    "git:"
    "jq:"
    "bash:4"
    "python3:3.11"
    "curl:"
)

# Optional tools. gh is required only when we'll fork; k3d is required only
# after cluster-bootstrap. We check presence but never gate on these.
OPTIONAL=("gh" "k3d")

declare -a MISSING=()
declare -a TOO_OLD=()

# Extract a parseable version string from a tool. Different tools have
# wildly different `--version` output, so we have a small case statement.
tool_version() {
    local tool="$1"
    case "$tool" in
        kubectl)
            kubectl version --client --output=json 2>/dev/null \
                | jq -r '.clientVersion.gitVersion // empty' 2>/dev/null \
                | sed 's/^v//'
            ;;
        helm)
            helm version --short 2>/dev/null \
                | sed -E 's/^v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/'
            ;;
        bash)
            # ${BASH_VERSION} is "5.1.16(1)-release"; strip the suffix.
            printf '%s\n' "${BASH_VERSION%%[!0-9.]*}"
            ;;
        python3)
            python3 -c 'import platform; print(platform.python_version())' 2>/dev/null
            ;;
        git)
            git --version 2>/dev/null | awk '{print $3}'
            ;;
        jq)
            # `jq --version` prints e.g. "jq-1.7.1".
            jq --version 2>/dev/null | sed -E 's/^jq-?//'
            ;;
        curl)
            curl --version 2>/dev/null | head -n1 | awk '{print $2}'
            ;;
        gh)
            gh --version 2>/dev/null | head -n1 | awk '{print $3}'
            ;;
        k3d)
            k3d version 2>/dev/null | head -n1 | awk '{print $3}' | sed 's/^v//'
            ;;
        *)
            "$tool" --version 2>/dev/null | head -n1
            ;;
    esac
}

# Returns 0 if $1 >= $2 (version comparison via `sort -V`). An empty $2
# means "no minimum required".
version_ge() {
    local have="$1" want="$2"
    [[ -z "$want" ]] && return 0
    [[ -z "$have" ]] && return 1
    local smallest
    smallest="$(printf '%s\n%s\n' "$have" "$want" | sort -V | head -n1)"
    [[ "$smallest" == "$want" ]]
}

# Build up a JSON document with jq. We start from {} and add each tool.
json='{}'

check_one() {
    local entry="$1" optional="${2:-false}"
    local tool="${entry%%:*}"
    local min="${entry#*:}"
    [[ "$min" == "$tool" ]] && min=""   # entries with no colon (optionals).

    local ver=""
    local ok="false"
    local note=""

    if ! command -v "$tool" >/dev/null 2>&1; then
        if [[ "$optional" == "true" ]]; then
            warn "$tool not found (optional — skipping)"
            note="missing-optional"
        elif [[ "${OBSERVIBELITY_NO_INSTALL:-}" == "1" ]]; then
            err "$tool missing — install with: $(pkg_install_hint "$tool" 2>/dev/null || echo "<see os.sh>")"
            MISSING+=("$tool")
            note="missing"
        else
            if ask_yn "Install $tool to ./tools/bin/ now?" Y; then
                if pkg_install "$tool"; then
                    # Re-check after install.
                    if command -v "$tool" >/dev/null 2>&1; then
                        ver="$(tool_version "$tool")"
                        ok="true"
                    else
                        MISSING+=("$tool")
                        note="install-did-not-place-on-path"
                    fi
                else
                    MISSING+=("$tool")
                    note="install-failed"
                fi
            else
                MISSING+=("$tool")
                note="user-declined-install"
            fi
        fi
    else
        ver="$(tool_version "$tool")"
        if version_ge "$ver" "$min"; then
            ok="true"
        else
            ok="false"
            note="too-old (want >= ${min:-any}, have ${ver:-unknown})"
            TOO_OLD+=("$tool")
            warn "$tool version ${ver:-unknown} is older than ${min}; will try anyway"
        fi
    fi

    json="$(jq --arg t "$tool" \
                --arg v "${ver:-}" \
                --arg m "${min:-}" \
                --arg o "$ok" \
                --arg n "${note:-}" \
                --argjson opt "$([[ $optional == true ]] && echo true || echo false)" \
                '. + {($t): {version: $v, min: $m, ok: ($o == "true"), optional: $opt, note: $n}}' \
                <<< "$json")"
}

step "check-binaries" "scanning required tools"
for entry in "${REQUIRED[@]}"; do
    check_one "$entry" false
done

step "check-binaries" "scanning optional tools"
# Skip gh entirely if user opted out of forking.
for tool in "${OPTIONAL[@]}"; do
    if [[ "$tool" == "gh" && "${OBSERVIBELITY_NO_FORK:-}" == "1" ]]; then
        continue
    fi
    check_one "$tool" true
done

# Persist as JSON. state_set_json accepts a raw JSON value, so we feed our
# accumulated document straight in.
state_set_json preflight.binaries "$json"

if [[ "${#MISSING[@]}" -gt 0 ]]; then
    err "Missing required tools: ${MISSING[*]}"
    exit 1
fi

if [[ "${#TOO_OLD[@]}" -gt 0 ]]; then
    warn "Older-than-recommended tools present: ${TOO_OLD[*]}"
fi

ok "All required binaries present."
exit 0
