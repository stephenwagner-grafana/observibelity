#!/usr/bin/env bats
# Tests for tools/lib/state.sh — the shared JSON state helper.

setup() {
    SRC_REPO="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    export SRC_REPO
    export REPO_ROOT="${BATS_TEST_TMPDIR}"
    export OBSERVIBELITY_STATE_DIR="${BATS_TEST_TMPDIR}/.observibelity-state"

    mkdir -p "${BATS_TEST_TMPDIR}/tools/lib"
    if [ -f "${SRC_REPO}/tools/lib/state.sh" ]; then
        cp "${SRC_REPO}/tools/lib/state.sh" "${BATS_TEST_TMPDIR}/tools/lib/state.sh"
    fi
    if [ -f "${SRC_REPO}/tools/lib/logging.sh" ]; then
        cp "${SRC_REPO}/tools/lib/logging.sh" "${BATS_TEST_TMPDIR}/tools/lib/logging.sh"
    fi

    cd "${BATS_TEST_TMPDIR}"
}

teardown() {
    cd "${BATS_TEST_DIRNAME}"
}

_load_state_lib() {
    if [ ! -f "${BATS_TEST_TMPDIR}/tools/lib/state.sh" ]; then
        return 1
    fi
    # shellcheck disable=SC1090
    [ -f "${BATS_TEST_TMPDIR}/tools/lib/logging.sh" ] && source "${BATS_TEST_TMPDIR}/tools/lib/logging.sh"
    # shellcheck disable=SC1090
    source "${BATS_TEST_TMPDIR}/tools/lib/state.sh"
    return 0
}

@test "state_init creates JSON file with version" {
    if ! _load_state_lib; then
        skip "lib/state.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash -c "
        source '${BATS_TEST_TMPDIR}/tools/lib/state.sh'
        state_init
        cat '${OBSERVIBELITY_STATE_DIR}/state.json'
    "
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "version" ]]
}

@test "state_get returns empty for missing key" {
    if ! _load_state_lib; then
        skip "lib/state.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash -c "
        source '${BATS_TEST_TMPDIR}/tools/lib/state.sh'
        state_init
        state_get 'nonexistent.key'
    "
    [[ "$status" -eq 0 ]]
    [[ -z "$output" || "$output" == "null" || "$output" == "" ]]
}

@test "state_set + state_get roundtrip a string value" {
    if ! _load_state_lib; then
        skip "lib/state.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash -c "
        source '${BATS_TEST_TMPDIR}/tools/lib/state.sh'
        state_init
        state_set 'inputs.color' 'orange'
        state_get 'inputs.color'
    "
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "orange" ]]
}

@test "state_set_json + state_get a nested object" {
    if ! _load_state_lib; then
        skip "lib/state.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash -c "
        source '${BATS_TEST_TMPDIR}/tools/lib/state.sh'
        state_init
        state_set_json 'cluster' '{\"kind\":\"k3s\",\"version\":\"1.29\"}'
        state_get 'cluster.kind'
    "
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "k3s" ]]
}

@test "state_mark_passed records timestamp" {
    if ! _load_state_lib; then
        skip "lib/state.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash -c "
        source '${BATS_TEST_TMPDIR}/tools/lib/state.sh'
        state_init
        state_mark_passed 'preflight.os'
        cat '${OBSERVIBELITY_STATE_DIR}/state.json'
    "
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ "preflight" ]]
    # ISO-8601 year prefix; loose check tolerates any 20xx timestamp
    [[ "$output" =~ 20[0-9][0-9]- ]]
}

@test "state_has_passed exits 0 after mark" {
    if ! _load_state_lib; then
        skip "lib/state.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash -c "
        source '${BATS_TEST_TMPDIR}/tools/lib/state.sh'
        state_init
        state_mark_passed 'preflight.binaries'
        state_has_passed 'preflight.binaries'
    "
    [[ "$status" -eq 0 ]]
}

@test "state_reset moves file to backup and reinits" {
    if ! _load_state_lib; then
        skip "lib/state.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash -c "
        source '${BATS_TEST_TMPDIR}/tools/lib/state.sh'
        state_init
        state_set 'inputs.flag' 'beforereset'
        state_reset
        # After reset, the old value must not survive
        state_get 'inputs.flag'
    "
    [[ "$status" -eq 0 ]]
    [[ ! "$output" =~ "beforereset" ]]
    # And a backup should exist
    run bash -c "ls '${OBSERVIBELITY_STATE_DIR}'/state.json.bak* 2>/dev/null || ls '${OBSERVIBELITY_STATE_DIR}'/*.bak 2>/dev/null"
    [[ "$status" -eq 0 ]]
}
