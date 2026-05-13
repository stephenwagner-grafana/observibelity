# shellcheck shell=bash
# ObserVIBElity shared lib: JSON-backed state file via jq (phase progress, inputs, preflight).

source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"

# Backing file. Caller must have REPO_ROOT exported unless OBSERVIBELITY_STATE_FILE
# is set. The ${REPO_ROOT:?...} guarantees a clear error if unset.
: "${OBSERVIBELITY_STATE_FILE:=${REPO_ROOT:?REPO_ROOT must be set by caller}/.observibelity-state}"

# _state_jq_path "a.b.c" -> ".a.b.c". Internal helper, callers shouldn't use.
_state_jq_path() {
    local dotted="$1"
    local part
    local path=""
    IFS='.' read -r -a _parts <<< "${dotted}"
    for part in "${_parts[@]}"; do
        path+=".${part}"
    done
    printf '%s' "${path}"
}

# state_init — create state file with the initial structure if missing.
state_init() {
    if [[ -f "${OBSERVIBELITY_STATE_FILE}" ]]; then
        return 0
    fi
    local now
    now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    jq -n --arg created "${now}" \
        '{version:"0.1.0", created:$created, phase_passed:{}, preflight:{}, inputs:{}}' \
        > "${OBSERVIBELITY_STATE_FILE}" \
        || die "failed to initialize state file at ${OBSERVIBELITY_STATE_FILE}"
}

# state_get <dotted.key> — echo value (string) at path, or empty if absent.
state_get() {
    local key="$1"
    state_init
    local path
    path="$(_state_jq_path "${key}")"
    jq -r "${path} // empty" "${OBSERVIBELITY_STATE_FILE}"
}

# state_set <dotted.key> <value> — set string value at dotted path.
state_set() {
    local key="$1"
    local value="$2"
    state_init
    local path
    path="$(_state_jq_path "${key}")"
    local tmp="${OBSERVIBELITY_STATE_FILE}.tmp.$$"
    jq --arg v "${value}" "${path} = \$v" "${OBSERVIBELITY_STATE_FILE}" > "${tmp}" \
        || { rm -f "${tmp}"; die "state_set: jq failed for key ${key}"; }
    mv "${tmp}" "${OBSERVIBELITY_STATE_FILE}"
}

# state_set_json <dotted.key> <json> — set raw JSON value at dotted path.
state_set_json() {
    local key="$1"
    local json="$2"
    state_init
    local path
    path="$(_state_jq_path "${key}")"
    local tmp="${OBSERVIBELITY_STATE_FILE}.tmp.$$"
    jq --argjson v "${json}" "${path} = \$v" "${OBSERVIBELITY_STATE_FILE}" > "${tmp}" \
        || { rm -f "${tmp}"; die "state_set_json: jq failed for key ${key} (value must be valid JSON)"; }
    mv "${tmp}" "${OBSERVIBELITY_STATE_FILE}"
}

# state_has_passed <step> — exit 0 if .phase_passed[step] exists and is non-null.
state_has_passed() {
    local step="$1"
    state_init
    local result
    result="$(jq -r --arg k "${step}" '.phase_passed[$k] // empty' "${OBSERVIBELITY_STATE_FILE}")"
    [[ -n "${result}" ]]
}

# state_mark_passed <step> — record passing timestamp for step.
state_mark_passed() {
    local step="$1"
    state_init
    local now
    now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    local tmp="${OBSERVIBELITY_STATE_FILE}.tmp.$$"
    jq --arg k "${step}" --arg v "${now}" '.phase_passed[$k] = $v' "${OBSERVIBELITY_STATE_FILE}" > "${tmp}" \
        || { rm -f "${tmp}"; die "state_mark_passed: jq failed for ${step}"; }
    mv "${tmp}" "${OBSERVIBELITY_STATE_FILE}"
}

# state_reset — back up current state file with unix-ts suffix, then re-init.
state_reset() {
    if [[ -f "${OBSERVIBELITY_STATE_FILE}" ]]; then
        local ts
        ts="$(date -u +%s)"
        mv "${OBSERVIBELITY_STATE_FILE}" "${OBSERVIBELITY_STATE_FILE}.${ts}.bak" \
            || die "state_reset: could not back up state file"
    fi
    state_init
}
