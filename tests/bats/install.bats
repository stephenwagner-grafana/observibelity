#!/usr/bin/env bats
# Tests for install.sh entrypoint.
# Conventions: bats-core 1.5+.

setup() {
    # Locate source repo (one level up from tests/)
    SRC_REPO="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    export SRC_REPO

    # Copy install.sh + tools/ into the per-test tempdir for isolation.
    if [ -f "${SRC_REPO}/install.sh" ]; then
        cp "${SRC_REPO}/install.sh" "${BATS_TEST_TMPDIR}/install.sh"
        chmod +x "${BATS_TEST_TMPDIR}/install.sh"
    fi
    if [ -d "${SRC_REPO}/tools" ]; then
        cp -r "${SRC_REPO}/tools" "${BATS_TEST_TMPDIR}/tools"
    fi

    cd "${BATS_TEST_TMPDIR}"
    export REPO_ROOT="${PWD}"
    export PATH="${BATS_TEST_TMPDIR}:${PATH}"
}

teardown() {
    cd "${BATS_TEST_DIRNAME}"
}

@test "install.sh --help prints usage and exits 0" {
    if [ ! -x "${BATS_TEST_TMPDIR}/install.sh" ]; then
        skip "install.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run "${BATS_TEST_TMPDIR}/install.sh" --help
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ [Uu]sage ]]
}

@test "install.sh -h is the same as --help" {
    if [ ! -x "${BATS_TEST_TMPDIR}/install.sh" ]; then
        skip "install.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run "${BATS_TEST_TMPDIR}/install.sh" -h
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ [Uu]sage ]]
}

@test "install.sh with unknown subcommand exits 64" {
    if [ ! -x "${BATS_TEST_TMPDIR}/install.sh" ]; then
        skip "install.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run "${BATS_TEST_TMPDIR}/install.sh" not-a-real-subcommand
    [[ "$status" -eq 64 ]]
}

@test "install.sh reset clears .observibelity-state" {
    if [ ! -x "${BATS_TEST_TMPDIR}/install.sh" ]; then
        skip "install.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    # Seed state file
    mkdir -p "${BATS_TEST_TMPDIR}/.observibelity-state"
    echo '{"version":1,"inputs":{"stale":"data"}}' > "${BATS_TEST_TMPDIR}/.observibelity-state/state.json"
    run "${BATS_TEST_TMPDIR}/install.sh" reset
    [[ "$status" -eq 0 ]]
    # After reset, either the state.json is gone or it's been reinitialized
    if [ -f "${BATS_TEST_TMPDIR}/.observibelity-state/state.json" ]; then
        run grep -q '"stale"' "${BATS_TEST_TMPDIR}/.observibelity-state/state.json"
        [[ "$status" -ne 0 ]]
    fi
}

@test "install.sh --auto without .env exits 1 in preflight phase" {
    if [ ! -x "${BATS_TEST_TMPDIR}/install.sh" ]; then
        skip "install.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    # Ensure no .env exists
    rm -f "${BATS_TEST_TMPDIR}/.env"
    run "${BATS_TEST_TMPDIR}/install.sh" --auto
    [[ "$status" -eq 1 ]]
}

@test "install.sh advertises 'deploy' as a subcommand in --help" {
    if [ ! -x "${BATS_TEST_TMPDIR}/install.sh" ]; then
        skip "install.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    # We don't actually execute `deploy` here — Phase 0's "scaffolding only"
    # stub was removed in v0.3.0, and a real deploy needs a cluster + .env.
    # We only sanity-check the CLI surface: --help must list the deploy
    # subcommand so users know it exists.
    run "${BATS_TEST_TMPDIR}/install.sh" --help
    [[ "$status" -eq 0 ]]
    [[ "$output" =~ deploy ]]
}
